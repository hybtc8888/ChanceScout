"""Shared validation, locking and output helpers; no network access."""
import contextlib
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, urlsplit

def timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return parsed

def http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"https", "http"} and bool(parsed.hostname) and not any(c.isspace() for c in value)
    except ValueError:
        return False

def check(value, spec, path="record"):
    """Check the types/constraints used by this project's small schema."""
    types = spec.get("type", [])
    types = [types] if isinstance(types, str) else types
    actual = ("null" if value is None else "boolean" if isinstance(value, bool)
              else "object" if isinstance(value, dict) else "array" if isinstance(value, list)
              else "string" if isinstance(value, str) else "number")
    if types and actual not in types:
        raise ValueError(f"{path}: expected {types}, got {actual}")
    if "enum" in spec and value not in spec["enum"]:
        raise ValueError(f"{path}: unknown value {value!r}")
    if isinstance(value, dict):
        for key in spec.get("required", []):
            if key not in value:
                raise ValueError(f"{path}: missing {key}")
        for key, child in spec.get("properties", {}).items():
            if key in value:
                check(value[key], child, f"{path}.{key}")
    elif isinstance(value, list):
        if len(value) < spec.get("minItems", 0):
            raise ValueError(f"{path}: not enough items")
        for index, child in enumerate(value):
            check(child, spec.get("items", {}), f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value.strip()) < spec.get("minLength", 0):
            raise ValueError(f"{path}: empty string")
        if "pattern" in spec and not re.search(spec["pattern"], value):
            raise ValueError(f"{path}: invalid format")
        if spec.get("format") == "uri" and not http_url(value):
            raise ValueError(f"{path}: expected an HTTP(S) URL")
        if spec.get("format") == "date-time":
            timestamp(value)

def atomic_write(path, text):
    path = Path(path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                     prefix=".chancescout-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

@contextlib.contextmanager
def workspace_lock(workspace):
    with (workspace / ".chancescout.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            lock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            unlock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            lock = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            unlock = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        try:
            lock()
        except OSError as exc:
            raise ValueError("workspace is being updated by another run; retry after it finishes") from exc
        try:
            yield
        finally:
            handle.seek(0)
            unlock()

def md(value):
    text = html.escape(str(value), quote=False).replace("\n", " ")
    return re.sub(r"([\\`*_{\[\]}|])", r"\\\1", text)

def link(url, label):
    # URLs are validated separately; encode Markdown delimiters without changing their destination.
    return f"[{label}]({quote(url, safe=':/?&=#%+@~;,')})"

def read_json_records(path):
    text = Path(path).read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    records = json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(records, list):
        raise ValueError("input must be a JSON array or JSONL")
    return records
