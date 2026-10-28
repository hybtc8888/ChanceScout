# 记录与历史

输入为 JSON 数组或 JSONL，每批一种格式；统一入口自动识别：

```bash
python scripts/chancescout.py validate candidates.json
python scripts/chancescout.py ingest candidates.json --workspace chancescout-data
```

| 类型 | 协议与示例 | 稳定身份 | 历史 / 报告 |
|---|---|---|---|
| 公开机会 | [schema](../schemas/opportunity.schema.json) · [虚构例子](../examples/opportunities.example.json) | 主办方＋项目＋期次；已有显式ID保留 | `opportunities.jsonl` / `runs/` |
| 付费需求 | [schema](../schemas/demand-lead.schema.json) · [虚构例子](../examples/demand-leads.example.json) | `canonical_key`；任务和产品的归并方式见[研究说明](demand-research.md) | `demand-leads.jsonl` / `demand-runs/` |

可以共用一个历史工作目录。每批分别生成 `digest.md`、`observations.json` 和 `receipt.json`。两种格式不混在同一输入批次；空批默认按公开机会处理，可用 `--kind demand` 指定需求。

每期最终报告按 [简报模板](report-template.md) 汇总两类记录，固定交代公开机会、小红书和 Reddit 三路结果。Python 的批次简报作为归档明细，不代替整期汇总；没有推荐条目的来源也须保留覆盖状态。无文件能力时直接在对话交付同样结构。

## 字段与变化

公开机会记录规则、收益、资格、投入/权利、截止、参与入口与字段对应证据。`official_verified`表示所列事实来自官方来源，不代表已验证用户资格或成功报名。

付费需求记录客户、问题、买家原话、发布时间、来源、判断、未知项与下一步；可加 `lead_type`、`platform`、`budget`、`region`、`work_mode`、`deadline`。报价、地区、方式、截止和类型变化会标为更新。任务不因没有 SEO 而不能归档。

`first_seen_at`是首次发现，`last_checked_at`是复查时间，两者都不代替原始发布时间。`change`为 `new`、`updated`、`unchanged`；旧ID、首次发现时间、备注和未知自定义字段继续保留。记录省略的旧可选字段沿用；本批提供的证据/关键词/替代品/SEO列表替换该条旧列表，应提交完整的当前观察。

未在本批复查的旧条目只留历史，不进入本期报告。工具不解析任意自然语言截止、不判断买家或付款，也不联网；状态与推荐取舍由研究助手核对。写锁防止并发覆盖，历史原子替换。

## 示例与兼容

`demo`生成虚构公开机会；`demo --kind demand`生成虚构的小红书任务与 Reddit 产品需求。示例与真实记录放不同工作目录。旧的 `scripts/demand_leads.py validate/ingest/demo`命令保留，统一文档只需使用 `scripts/chancescout.py`。

无 Python 时，宿主文件或文档工具可按相同含义维护历史；无持久存储时交付可保存 JSON，说明单次模式。
