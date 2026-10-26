# Opportunity Radar · 机会雷达

把这个仓库交给你的 AI 助手，让它找出**仍可参与、有官方依据、值得行动的公开机会**。

默认关注 AI 开发和内容创作，也能按你的需求寻找比赛、资助、算力支持、创作征集或合作招募。

## 发给 Dot、Muse 或其他助手

复制下面这段即可。助手不必支持技能安装：能读取网页、理解指令，就能先按说明工作。

```text
请阅读 https://github.com/hybtc8888/opportunity-radar 的 SKILL.md，按机会雷达工作流执行。
先检查你实际能用的联网、网页读取、文件存储和代码执行能力。
手动找一期 AI 开发与内容创作机会，优先个人或小团队能参与的项目。
核验官方规则、时间、资格、收益和参与路线，说明未知项，不凑数。
有持久存储就读取并更新已有记录；没有就交付本期简报及可保存的 JSON，明确是单次模式。
不要自动建立定时任务，不代我报名、投稿、付款或联系主办方。
```

如果助手打不开 GitHub 页面，可改发原始入口：

https://raw.githubusercontent.com/hybtc8888/opportunity-radar/main/SKILL.md

## 怎样运行

```text
你给出方向 → 助手联网发现线索 → 打开官方规则核验
         → 与历史比较 → 生成简报 → 保存记录或交付文件
```

- **助手**负责搜索、读来源和判断；本项目不附带某一家模型或搜索服务。
- **技能**提供可移植的操作说明，可装进 Codex，也可当作普通文档交给其他助手。
- **可选 Python 工具**负责验证记录格式、去重、保留历史和生成简报，不替助手完成事实核验。

| 助手具备的能力 | 可以做什么 |
|---|---|
| 搜索 + 读取官方网页 | 单次雷达，标出核验范围 |
| 再有持久文件或文档存储 | 跨次去重、识别规则变化 |
| 再能运行 Python 3.11+ | 使用本项目工具稳定合并记录、生成报告 |
| 没有联网能力 | 只能整理用户提供的材料，不能声称查到了当前机会 |

Dot 可使用已连接电脑上的 Codex；云端助手也可直接读工作流。具体产品的工具、账号权限和存储方式由宿主提供。Muse 等产品按上述能力适配，**未声称所有产品均已完成端到端测试**。参见 [宿主接入](docs/hosts.md)。

## 本地运行示例

Python 工具仅使用标准库，不需要安装依赖或配置 API Key。

```bash
git clone https://github.com/hybtc8888/opportunity-radar.git
cd opportunity-radar
python scripts/radar.py demo --workspace radar-demo
```

这会生成**明确标注虚构**的示例报告，不会联网或报名。

真实使用时，由助手按 [记录格式](references/records.md) 输出候选 JSON，然后运行：

```bash
python scripts/radar.py validate candidates.json
python scripts/radar.py ingest candidates.json --workspace radar-data
```

每次运行输出 JSON 回执，包含报告、观察记录和历史文件路径。再次录入同一项目不会重复；规则变化会标为更新，未复查的旧项目不会混入本期推荐。

可将 [config.example.json](config.example.json) 复制为工作目录下的 `config.json`，调整主题、时区、数量偏好和语言。助手读取这些偏好；Python 工具只负责存储与排版。`target_total` 不是配额。

## 安装为 Codex 技能

让 Codex 使用其技能安装器安装本仓库根目录的 `SKILL.md`，技能名为 `opportunity-radar`。也可将完整仓库放入宿主支持的技能目录。保留 `references/`、`schemas/` 和 `scripts/`。

使用：`使用 $opportunity-radar，手动更新一期 AI 开发与内容创作机会。`

## 结果应包含什么

每个机会写清：收益类型、参与门槛、必要投入、报名与提交截止、官方依据、参与路线、未确认部分及下一步。现金与额度、总奖池与个人收益、能打开页面与能完成报名分别说明。

默认只检索公开信息并保存结果。需要登录、报名或投稿时由用户决定后续操作；定时执行也由用户另行要求并交给宿主实现。

## 开发与验证

```bash
python -m unittest discover -s tests -v
```

测试覆盖去重、更新、用户备注保留、批次报告、示例隔离与失败写入。GitHub Actions 在 Windows、macOS、Linux 运行相同检查。

本项目采用 [MIT License](LICENSE)。来源与实现范围见 [NOTICE](NOTICE.md)。欢迎提交能复现问题的输入，先移除个人画像、登录信息和真实运行记录。
