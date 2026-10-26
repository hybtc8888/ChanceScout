#!/usr/bin/env python3
"""Portable observation storage. No network, model calls, or scheduling."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from urllib.parse import quote, urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/opportunity.schema.json").read_text(encoding="utf-8"))
MATERIAL = set(SCHEMA["required"]) - {"evidence"}
MATERIAL.update({"application_url", "recommended"})


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


def identity(record):
    if record.get("id"):
        return record["id"]
    parts = [" ".join(unicodedata.normalize("NFKC", record[k]).casefold().split())
             for k in ("organizer", "program", "edition")]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]


def validate(records):
    seen = set()
    for index, record in enumerate(records):
        check(record, SCHEMA, f"record[{index}]")
        if record["evidence_level"] != "unverified" and not record["evidence"]:
            raise ValueError(f"record[{index}]: verified facts need field-linked evidence")
        key = identity(record)
        if key in seen:
            raise ValueError(f"duplicate observation for {key}; consolidate the same edition before ingest")
        seen.add(key)


def read_records(path):
    text = Path(path).read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    values = json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(values, list):
        raise ValueError("input must be a JSON array or JSONL")
    validate(values)
    return values


def comparable(record):
    result = {key: record.get(key) for key in MATERIAL}
    result["recommended"] = record.get("recommended", True)
    for key in ("source_urls", "limitations"):
        result[key] = sorted(result.get(key) or [])
    return result


def merge(existing, incoming, checked_at):
    timestamp(checked_at)
    validate(existing)
    validate(incoming)
    by_id = {identity(record): dict(record) for record in existing}
    observed = []
    for value in incoming:
        current = dict(value)
        key = identity(current)
        old = by_id.get(key)
        current["id"] = key
        current["last_checked_at"] = current.get("last_checked_at", checked_at)
        current["first_seen_at"] = (old or {}).get("first_seen_at", current.get("first_seen_at", current["last_checked_at"]))
        current = {**(old or {}), **current}
        current["change"] = "new" if old is None else "updated" if comparable(old) != comparable(current) else "unchanged"
        by_id[key] = current
        observed.append(current)
    return list(by_id.values()), observed


def atomic_write(path, text):
    path = Path(path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                     prefix=".radar-", delete=False) as handle:
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
    with (workspace / ".state.lock").open("a+b") as handle:
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


def is_main(record):
    return (record["status"] in {"open", "ongoing"}
            and record["evidence_level"] != "unverified"
            and record.get("recommended", True))


def render(observed, generated_at, fictional=False):
    title = "虚构示例 · 不可申请" if fictional else "机会雷达"
    lines = [f"# {title}", "", f"生成时间：{generated_at}", "",
             "本工具校验格式并整理记录；来源事实由研究助手核验。首次发现不等于首次发布。", "",
             f"本期观察 {len(observed)} 条；主要机会 {sum(is_main(r) for r in observed)} 条。", ""]
    if fictional:
        lines += ["**全部组织、机会、链接、日期和核验状态均为虚构演示，不可申请。**", ""]
    groups = [
        ("主要机会", [r for r in observed if is_main(r)]),
        ("即将开放", [r for r in observed if r["status"] == "upcoming" and r["evidence_level"] != "unverified"]),
        ("待核验、受限或关闭", [r for r in observed if not is_main(r) and not (r["status"] == "upcoming" and r["evidence_level"] != "unverified")]),
    ]
    for heading, records in groups:
        lines += [f"## {heading}", ""]
        if not records:
            lines += ["本期没有可列条目。", ""]
        for record in records:
            sources = " · ".join(link(url, f"来源{i + 1}") for i, url in enumerate(record["source_urls"]))
            route = link(record["application_url"], "参与入口") if record.get("application_url") else "按官方指引"
            lines += [f"### {md(record['program'])}", "",
                      f"- 主办方 / 期次：{md(record['organizer'])} / {md(record['edition'])}",
                      f"- 状态 / 本次变化：{record['status']} / {record['change']}；方向：{md(record['channel'])}",
                      f"- 收益：{md(record['benefit'])}", f"- 资格：{md(record['eligibility'])}",
                      f"- 投入与权利：{md(record['costs_and_rights'])}", f"- 截止：{md(record['deadline'])}",
                      f"- 路线：{route}；{md(record['application_instructions'])}",
                      f"- 核验：{record['evidence_level']}；入口检查：{record['application_access']}；最近检查：{record['last_checked_at']}",
                      f"- 未确认部分：{md('；'.join(record['limitations']) or '记录未列出，不能据此推断所有事项均已核验')}",
                      f"- 下一步：{md(record['next_action'])}", f"- 依据：{sources}", ""]
    lines += ["历史中未在本批次重新观察的项目不作为本期推荐。未执行报名、付款、投稿、发信或定时任务。", ""]
    return "\n".join(lines)


def ingest(incoming, workspace, checked_at=None, demo=False):
    validate(incoming)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    checked_at = checked_at or now
    timestamp(checked_at)
    workspace = Path(workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    with workspace_lock(workspace):
        state = workspace / "opportunities.jsonl"
        existing = read_records(state) if state.exists() else []
        flags = {bool(record.get("fictional", False)) for record in existing + incoming}
        if len(flags) > 1 or (demo and flags and flags != {True}):
            raise ValueError("keep fictional examples and real observations in separate workspaces")
        fictional = flags == {True} or demo
        merged, observed = merge(existing, incoming, checked_at)
        run = workspace / "runs" / (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
        run.mkdir(parents=True)
        report = run / "digest.md"
        atomic_write(report, render(observed, now, fictional))
        atomic_write(run / "observations.json", json.dumps(observed, ensure_ascii=False, indent=2) + "\n")
        receipt = {"report": str(report), "observations": str(run / "observations.json"), "history": str(state),
                   "observed": len(observed), "history_count": len(merged), "main_opportunities": sum(is_main(r) for r in observed),
                   "new": sum(r["change"] == "new" for r in observed), "updated": sum(r["change"] == "updated" for r in observed),
                   "unchanged": sum(r["change"] == "unchanged" for r in observed), "fictional": fictional}
        atomic_write(run / "receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        atomic_write(state, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged))
        return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate_cmd = sub.add_parser("validate", help="check observation data; no network or file changes")
    validate_cmd.add_argument("input", type=Path)
    ingest_cmd = sub.add_parser("ingest", help="merge researched observations and write a report")
    ingest_cmd.add_argument("input", type=Path)
    ingest_cmd.add_argument("--workspace", type=Path, default=Path("radar-data"))
    ingest_cmd.add_argument("--checked-at", help="timezone-aware observation time, if not present in each record")
    demo_cmd = sub.add_parser("demo", help="write a clearly fictional offline example")
    demo_cmd.add_argument("--workspace", type=Path, default=Path("radar-demo"))
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            result = {"valid": True, "records": len(read_records(args.input)), "facts_verified_by_tool": False}
        elif args.command == "demo":
            result = ingest(read_records(ROOT / "examples/opportunities.example.json"), args.workspace, demo=True)
        else:
            result = ingest(read_records(args.input), args.workspace, args.checked_at)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
