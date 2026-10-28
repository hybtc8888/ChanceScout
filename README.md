# ChanceScout · AI找路子

把 ChanceScout 交给 AI 助手，查找有来源、仍值得行动的机会与付费需求。

| 来源 | 怎么找 | 怎么判断 |
|---|---|---|
| 官方网站 | 比赛、资助、资源支持、征集与合作 | 核对规则、收益、资格、截止和参与入口 |
| 小红书 | 搜“付费”“有偿”，最新优先 | 找愿意花钱委托具体任务的买家，排除卖家广告与失效需求 |
| Reddit | 搜“I would pay”“willing to pay”“I'd pay” | 读原帖与评论，区分有偿任务和产品需求，核对替代品 |

首次部署询问方向、地区、远程/线下及时间窗口。可以全部留空：直接跨领域、跨地区检索；付费需求默认近 7 天、最新优先。以后随时修改，保留历史。

## 发给 Codex、Dot、Muse 或其他助手

```text
请读取 https://github.com/hybtc8888/ChanceScout 的 SKILL.md，按 ChanceScout 工作流手动运行一期。
首次使用询问一次可选偏好；未提供就返回泛用结果，不等待补填。
覆盖可用的小红书、Reddit 和公开机会来源，说明每个来源实际检查到哪里。
交付按时效整理的机会、付费任务、产品需求与待核验项，附来源和下一步，不凑数。
有历史就复用，没有持久存储就交付可保存的 JSON 并说明单次模式。
不建立定时任务，不代我联系、报名、投稿或付款。
```

打不开 GitHub 页面时，使用 [原始技能入口](https://raw.githubusercontent.com/hybtc8888/ChanceScout/main/SKILL.md)。宿主能力、部署设定与迁移见 [接入说明](docs/hosts.md)。

助手负责搜索、读原文和判断；项目不绑定模型、搜索服务或 SEO 账号。需求表达不等于成交，能打开帖子不等于仍有名额。

## 推荐浏览器接入

需要读取已登录的小红书页面时，推荐可选安装 [huashu-chrome（花叔浏览器扩展）](https://github.com/alchaincyf/huashu-chrome)：它通过 Chrome 扩展和本地 MCP 服务，让助手使用现有登录状态。按上游说明安装后，让实际执行任务读取页面正文并截图验证。

不使用 Chrome 时，继续使用宿主已有的浏览器工具；访问不到的来源如实标记。ChanceScout 不强制安装扩展，不要求开启 TUN。安装步骤、Dot 交接和超时排查见 [浏览器接入](docs/browser.md)。

## 可选的本地工具

Python 3.11+，仅用标准库。助手完成研究后，用一个入口整理两类数据：

```bash
python scripts/chancescout.py validate candidates.json
python scripts/chancescout.py ingest candidates.json --workspace chancescout-data
```

工具自动识别 [公开机会](schemas/opportunity.schema.json) 和 [付费需求](schemas/demand-lead.schema.json)；每批使用一种格式。两类历史可放在同一工作目录，旧 ID、首次发现时间和备注继续保留。它不联网，也不替助手判断时效或设置偏好。

离线试用（全部虚构）：

```bash
python scripts/chancescout.py demo
python scripts/chancescout.py demo --kind demand
```

首次运行按需保存 [配置模板](config.example.json) 为 `config.json`。格式、历史与兼容命令见 [记录说明](references/records.md)。真实记录、个人配置和运行产物默认不进入 Git。

## 安装与验证

Codex 可用技能安装器安装本仓库根目录，名称为 `chancescout`；其他助手直接读取工作流。使用：`使用 $chancescout，手动找一期机会和付费需求。`

```bash
python -m unittest discover -s tests -v
```

本地 Codex 已完成 Reddit 与小红书研究试跑；本机 Dot 已通过花叔 MCP 入口完成小红书研究及正文、截图验收。具体账号、版本与工具仍需在目的宿主验证，Muse 尚未实测。GitHub Actions 检查 Windows、macOS、Linux 的本地工具。

[MIT License](LICENSE) · [来源与实现范围](NOTICE.md)
