#!/usr/bin/env python3
"""Store researched demand leads. No search, semantic verification, APIs or scheduling."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import sys
import uuid

import common as storage

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/demand-lead.schema.json").read_text(encoding="utf-8"))
METRICS = ("volume", "global_volume", "kd", "cpc")
LABELS = {"direct": "直接读取", "author_screenshot": "作者截图，未独立复现", "unavailable": "未取得"}
LEAD_TYPES = {"task": "有偿任务", "product": "产品需求", "unknown": "未分类需求"}
DETAILS = {"budget": "报价", "region": "地区", "work_mode": "方式", "deadline": "截止/时间要求"}


def identity(record):
    if record.get("id"):
        return record["id"]
    return hashlib.sha256(record["canonical_key"].encode("utf-8")).hexdigest()[:20]


def validate(records):
    seen = set()
    seen_keys = set()
    for index, record in enumerate(records):
        storage.check(record, SCHEMA, f"lead[{index}]")
        key = identity(record)
        if key in seen or record["canonical_key"] in seen_keys:
            raise ValueError("duplicate canonical_key; consolidate evidence for the same customer/problem")
        seen.add(key)
        seen_keys.add(record["canonical_key"])
        for row in record["seo"]:
            for field in METRICS:
                value = row[field]
                if value is not None and (isinstance(value, bool) or not math.isfinite(value)
                                          or value < 0 or (field == "kd" and value > 100)):
                    raise ValueError(f"invalid SEO {field}: {value!r}")
                if field in {"volume", "global_volume"} and value is not None and value != int(value):
                    raise ValueError("search volume must be a whole number")
            if row["retrieval"] == "unavailable" and any(row[k] is not None for k in METRICS):
                raise ValueError("unavailable metrics must be null, not zero or guessed values")
            if any(row[k] is not None for k in METRICS) and row["period"] is None:
                raise ValueError("measured metrics need their data month")
            if row["cpc"] is not None and row["currency"] is None:
                raise ValueError("CPC needs its currency")
            if row["market"].casefold() in {"global", "worldwide"} and any(row[k] is not None for k in ("volume", "kd", "cpc")):
                raise ValueError("keep country volume/KD/CPC separate from global_volume")


def read_records(path):
    values = storage.read_json_records(path)
    validate(values)
    return values


def comparable(record):
    fields = set(SCHEMA["required"]) | set(DETAILS) | {"lead_type", "platform"}
    return {key: record.get(key) for key in fields}


def merge(existing, incoming, checked_at):
    storage.timestamp(checked_at)
    validate(existing)
    validate(incoming)
    by_id = {identity(r): dict(r) for r in existing}
    by_key = {r["canonical_key"]: r for r in existing}
    observed = []
    for value in incoming:
        old = by_key.get(value["canonical_key"])
        key = identity(old) if old is not None else identity(value)
        if value.get("id") and value["id"] != key:
            raise ValueError("canonical_key already belongs to a different ID")
        if key in by_id and by_id[key]["canonical_key"] != value["canonical_key"]:
            raise ValueError("ID already belongs to a different canonical_key")
        current = {**(old or {}), **value, "id": key}
        current["last_checked_at"] = value.get("last_checked_at", checked_at)
        current["first_seen_at"] = (old or {}).get("first_seen_at", value.get("first_seen_at", current["last_checked_at"]))
        current["change"] = "new" if old is None else "updated" if comparable(old) != comparable(current) else "unchanged"
        by_id[key] = current
        observed.append(current)
    return list(by_id.values()), observed


def metric(value):
    return "未取得" if value is None else str(value)


def render(observed, generated_at, fictional=False):
    md, link = storage.md, storage.link
    lines = ["# ChanceScout · AI找路子 · 付费需求" + (" · 虚构示例" if fictional else ""), "",
             f"生成时间：{generated_at}", "",
             "需求表达、广告出价和搜索量不等于成交。人物角色、信号和取舍由研究助手判断，脚本只整理记录。", "",
             f"本批 {len(observed)} 条；继续研究 {sum(r['disposition'] == 'research' for r in observed)} 条；不纳入 {sum(r['disposition'] == 'discarded' for r in observed)} 条。", ""]
    if fictional:
        lines += ["**全部例子为虚构，不是当前商业机会。**", ""]
    for disposition, heading in (("research", "继续研究"), ("discarded", "不纳入及原因")):
        lines += [f"## {heading}", ""]
        for record in observed:
            if record["disposition"] != disposition:
                continue
            lines += [f"### {md(record['title'])}", "",
                      f"- 类型 / 来源：{LEAD_TYPES[record.get('lead_type', 'unknown')]} / {md(record.get('platform', '未注明'))}",
                      f"- 客户：{md(record['customer'])}",
                      f"- 问题：{md(record['problem'])}", f"- 判断：{md(record['assessment'])}",
                      f"- 变化：{record['change']}；首次发现：{record['first_seen_at']}；最近复查：{record['last_checked_at']}"]
            for field, label in DETAILS.items():
                if field in record or record.get("lead_type") == "task":
                    value = record.get(field)
                    if field == "work_mode":
                        value = {"any": "不限", "remote": "远程", "onsite": "线下", "hybrid": "混合"}.get(value, "未知")
                    lines += [f"- {label}：{md(value or '未知')}"]
            lines += [""]
            for e in record["evidence"]:
                published = e["published_at"] or "发布时间未取得"
                lines += [f"> {md(e['quote'])}", "", f"{link(e['url'], '原始依据')} · {published} · {e['speaker']} / {e['signal']} · {e['access']}",
                          f"上下文：{md(e['context'])}", ""]
            lines += ["关键词：" + md("；".join(record["keywords"]) or "未提取"), ""]
            for a in record["alternatives"]:
                lines += [f"- 替代品：{link(a['url'], md(a['name']))}；{md(a['finding'])}"]
            if record["seo"]:
                lines += ["", "SEO 证据：", ""]
            elif record.get("lead_type") == "product":
                lines += ["", "SEO 指标：未取得。", ""]
            for row in record["seo"]:
                lines += [f"- {md(row['keyword'])} · {md(row['provider'])} · {md(row['market'])} · {row['period'] or '月份未知'} · {LABELS[row['retrieval']]}",
                          f"  市场月搜索量 {metric(row['volume'])}；全球月搜索量 {metric(row['global_volume'])}；KD {metric(row['kd'])}；CPC {metric(row['cpc'])} {row['currency'] or ''}。",
                          f"  {link(row['source_url'], '指标来源')}；{md(row['note'])}"]
            lines += ["", f"未确认：{md('；'.join(record['limitations']) or '记录未列出')}",
                      f"下一步：{md(record['next_action'])}", ""]
    return "\n".join(lines)


def ingest(incoming, workspace, checked_at=None, demo=False):
    validate(incoming)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    checked_at = checked_at or now
    storage.timestamp(checked_at)
    workspace = Path(workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    with storage.workspace_lock(workspace):
        state = workspace / "demand-leads.jsonl"
        existing = read_records(state) if state.exists() else []
        flags = {r.get("fictional", False) for r in existing + incoming}
        if len(flags) > 1 or (demo and flags and flags != {True}):
            raise ValueError("keep fictional and real demand leads in separate workspaces")
        fictional = demo or flags == {True}
        merged, observed = merge(existing, incoming, checked_at)
        run = workspace / "demand-runs" / (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
        run.mkdir(parents=True)
        report = run / "digest.md"
        storage.atomic_write(report, render(observed, now, fictional))
        storage.atomic_write(run / "observations.json", json.dumps(observed, ensure_ascii=False, indent=2) + "\n")
        receipt = {"report": str(report), "history": str(state), "observed": len(observed), "history_count": len(merged),
                   "research": sum(r["disposition"] == "research" for r in observed),
                   "discarded": sum(r["disposition"] == "discarded" for r in observed),
                   **{k: sum(r["change"] == k for r in observed) for k in ("new", "updated", "unchanged")},
                   "fictional": fictional, "facts_verified_by_tool": False}
        storage.atomic_write(run / "receipt.json", json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        storage.atomic_write(state, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged))
        return receipt


def main(argv=None):
    # Compatibility entrypoint; the shared CLI owns argument parsing.
    from chancescout import main as run
    return run(argv, default_kind="demand")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
