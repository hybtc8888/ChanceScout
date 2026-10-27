#!/usr/bin/env python3
"""ChanceScout observation storage. No network, model calls, or scheduling."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import unicodedata
import uuid

from common import timestamp, http_url, check, atomic_write, workspace_lock, md, link, read_json_records

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/opportunity.schema.json").read_text(encoding="utf-8"))
MATERIAL = set(SCHEMA["required"]) - {"evidence"}
MATERIAL.update({"application_url", "recommended"})


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
    values = read_json_records(path)
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


def is_main(record):
    return (record["status"] in {"open", "ongoing"}
            and record["evidence_level"] != "unverified"
            and record.get("recommended", True))


def render(observed, generated_at, fictional=False):
    title = "ChanceScout · AI找路子 · 虚构示例 · 不可申请" if fictional else "ChanceScout · AI找路子"
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


def record_kind(records, requested="auto"):
    if requested != "auto":
        return requested
    kinds = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each observation must be an object")
        opportunity = "organizer" in record and "program" in record
        demand = "canonical_key" in record
        if opportunity == demand:
            raise ValueError("cannot infer record kind; supply --kind opportunity or --kind demand")
        kinds.add("opportunity" if opportunity else "demand")
    if len(kinds) > 1:
        raise ValueError("keep opportunities and demand leads in separate input batches")
    return next(iter(kinds), "opportunity")


def main(argv=None, default_kind="auto"):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate_cmd = sub.add_parser("validate", help="check observation data; no network or file changes")
    validate_cmd.add_argument("input", type=Path)
    ingest_cmd = sub.add_parser("ingest", help="merge researched observations and write a report")
    ingest_cmd.add_argument("input", type=Path)
    ingest_cmd.add_argument("--workspace", type=Path, default=Path("chancescout-data"))
    ingest_cmd.add_argument("--checked-at", help="timezone-aware observation time, if not present in each record")
    demo_cmd = sub.add_parser("demo", help="write a clearly fictional offline example")
    demo_cmd.add_argument("--workspace", type=Path, default=Path("chancescout-demo"))
    for command in (validate_cmd, ingest_cmd, demo_cmd):
        command.add_argument("--kind", choices=("auto", "opportunity", "demand"), default=default_kind,
                             help="infer the input format by default; demo defaults to opportunity")
    demo_cmd.set_defaults(workspace=None)
    args = parser.parse_args(argv)
    try:
        incoming = [] if args.command == "demo" else read_json_records(args.input)
        kind = record_kind(incoming, args.kind)
        validate_records, store_records = validate, ingest
        if kind == "demand":
            from demand_leads import validate as validate_records, ingest as store_records
        if args.command == "demo":
            fixture = "demand-leads" if kind == "demand" else "opportunities"
            workspace = args.workspace or Path("chancescout-demand-demo" if kind == "demand" else "chancescout-demo")
            incoming = read_json_records(ROOT / f"examples/{fixture}.example.json")
            validate_records(incoming)
            result = store_records(incoming, workspace, demo=True)
        elif args.command == "validate":
            validate_records(incoming)
            result = {"valid": True, "records": len(incoming), "facts_verified_by_tool": False}
        else:
            result = store_records(incoming, args.workspace, args.checked_at)
        result["kind"] = kind
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
