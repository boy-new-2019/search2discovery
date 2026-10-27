# search2discovery

**面向 Codex Desktop 的证据优先型研究发现与计划工作流**

[简体中文](#简体中文) · [English](#english)

<a id="简体中文"></a>

## 简介

**版本 1.0.0** · Python 3.11+ · Windows Codex Desktop · 用于研究规划，**不执行实验**

输入研究主题后，search2discovery 可帮助发现学术文献、检索合法公开的全文、执行结构化的多代理论文审读、检验潜在研究空白，并形成可证伪的研究问题、候选方法和实验计划，供研究者审阅。

它**不会**运行训练、实验、数值模拟、GPU 作业或方法测试，也不保证研究新颖性、科学结论正确性、期刊排名、模型可用性或付费 Codex 代理能够自主运行。

## 本次运行修正（runtime.2）

从主题出发时，技能会完成文献发现、机制比较、候选筛选与路线收敛；最终应给出**一条首选路线及具体方法**，同时解释被排除的方案。方法说明必须包含模型与数据、信息可用边界、表示与更新算子、目标函数、监督来源、公平基线、资源估计和放弃条件。若没有候选成立，应明确交付有证据的否定结论，不保证凭空产生创新。

- 支持“完整发现”“已有方向细化”“仅比较、不精读”三种范围，按当前请求执行。
- 新主题启用 arXiv、CVF、PMLR、OpenReview、Crossref、OpenAlex 六源检索；支持缓存、去重、续跑和单源故障后的替代检索。来源可用性与开放全文覆盖仍受各站点限制。
- OpenAlex 区分每秒限流、每日额度耗尽和不明 429；采用有限退避、服务端等待时间和持久暂停状态。不会轮换密钥绕过限制。
- 中文、英文和混合提示词统一按 Unicode 字符计预算；历史较大的预留值保留，不重置账本。重复收集或提交已完成任务会校验并复用回执。
- 满足准入条件的核心文献优先进入精读；未回答的科学问题进入后续推理。对同一缺口连续两批没有有效证据增益时，暂停该检索策略并复查。
- `campaign-plan` 在扩展筛选前核算各阶段需求。预算是本地派发上限，不能当作账户余额；新建研究推理配置可容纳完整九次专家派发，旧配置不自动增加。
- Python 3.11 字符串语法已修正；CI 同时测试 Windows / Ubuntu 与 Python 3.11 / 3.12。

### 全局安装后的首次使用

四个技能安装在同一全局技能目录后，公开入口自带项目安装器和 27 份代理配置。它可以在新研究目录中自动自举；也可以运行：

```powershell
# 按实际 Python 环境调整。此示例使用 conda。
$python = 'D:\anaconda\python.exe'
$skills = Join-Path $HOME '.codex/skills'
& $python (Join-Path $skills 'search2discovery/scripts/bootstrap.py') --project 'D:\ResearchWorkspace'
```

已有安装需要替换时使用 `--upgrade`；安装器备份代码并阻止覆盖未完成签名任务。然后在研究工作区调用 `$search2discovery`，说明主题、约束与预算。完整研究请求下，主代理应实际派发、等待并收集独立代理结果后继续，不应在每个小批次后只返回命令让用户接手。

```powershell
$ws = (Get-Location).Path
$s = Join-Path $ws '.agents/skills/research-cognition-engine/scripts/suite.py'
& $python $s campaign-plan --workspace $ws
```

新主题的最终产物新增 `research_discovery_package/route_selection.json` 与 `final_route_and_method.md`。方法字段、独立复核和来源检查由程序校验；科学解释是否正确、新颖性是否成立仍须结合原文和后续研究验证。

## 工作流

```text
研究主题与约束
  → 官方来源与会议状态（按年度缓存）及主题解析
  → 文献发现（CORE / RELATED / INSPIRATION 候选）
  → 合法开放全文检索及 S1/S2 筛选
  → R1–R5 原文阅读与独立终审
  → 可核查的证据台账、轮次报告和 SQLite 研究记忆
  → 跨论文比较、矛盾分析、候选假设与问题驱动的先前工作检索
  → 两份独立的新颖性风险审查与实验设计
  → 中文研究建议及尚未执行的实验计划
```

### 组件

| 组件 | 用途 |
| --- | --- |
| `paper-discovery-preflight/` | 六源学术检索、去重、合法公开全文及跨学科发现 |
| `batch-paper-deepread-desktop/` | S1/S2 筛选及五轮不同侧重点的全文审读与独立复核 |
| `research-cognition-engine/` | 研究记忆、研究问题检索、矛盾分析、假设评估、证据感知调度与报告 |
| `search2discovery/` | 唯一公开 Skill 入口：`$search2discovery` |
| `.codex/agents/` | 27 份 Codex Desktop 原生子代理配置；不代表 27 个代理会同时运行 |

内部引擎保留历史版本接口，以兼容既有研究数据和测试；公开产品版本为 **v1.0.0**。

## 快速开始（Windows PowerShell）

需要 Python **3.11+**、支持项目级 Skills 与原生代理的 Codex Desktop，以及可用的模型权限。PDF 文本提取建议安装 `pypdf`（BSD-3-Clause）：

```powershell
py -3 -m pip install "pypdf>=4"
```

可选的 PDF 图像渲染可能需要 PyMuPDF（`fitz`），其许可为 **AGPL-3.0 或商业许可**。该依赖未随项目打包；使用前请阅读其条款，详见[依赖与许可](docs/DEPENDENCIES.md)。

克隆或下载仓库后，将 Skill 安装到研究工作区：

```powershell
py -3 install.py --project "D:\ResearchWorkspace"
```

升级已有 v6.x 安装前，请先备份工作区并处理未完成的签名原生任务：

```powershell
py -3 install.py --project "D:\ResearchWorkspace" --upgrade
```

在 Codex Desktop 中打开 `D:\ResearchWorkspace`，然后输入：

```text
Use $search2discovery. My research topic is: [YOUR TOPIC].
Work from authentic sources. You may search academic metadata and download
legally accessible open-access PDFs. Keep the topic/approved methods frozen;
use S1/S2 and R1–R5 for admitted core papers; preserve independent checks.
Produce stage reports, defend research gaps against nearest prior art, and
finish with a Chinese report of research questions, candidate methods and
unexecuted experiment plans. Do NOT run experiments, training, or simulations.
Respect the local budget and resume verified checkpoints instead of repeating work.
```

Codex Desktop 需要在指定边界实际派发原生代理线程；本地 Python 工具不能独立调用订阅所含模型。新项目可能需要先审阅并确认模型生成的英文主题简报。遇到权限、来源缺失、审稿任务或配额限制时，工作流可能暂停；它不是一键无人值守服务。

### 不调用模型查看进度

```powershell
$ws = (Get-Location).Path
$s = Join-Path $ws '.agents\skills\research-cognition-engine\scripts\suite.py'
py -3 $s doctor --workspace $ws
py -3 $s topic-next --workspace $ws
py -3 $s round-reports --workspace $ws
py -3 $s smart-next --workspace $ws
py -3 $s official-status --workspace $ws
```

完整命令和权限关卡见[操作手册](docs/OPERATIONS.md)。

## 证据与质量规则

- 默认书目目标为 50 篇核心、150 篇相关和 50 篇跨学科的不同候选记录；这是目标，不保证检索成功，也不等同于 250 篇全文精读。
- 对纳入的核心论文先进行 S1/S2 筛选，再完成五轮不同侧重点的原文阅读。R3 只分析作者已发表的实验结果和明确标注为未执行的思想实验。
- DOI 或元数据匹配不等于全文证据；带页码的引文也不代表其解释已获独立验证。
- 重要假设会检索最接近的先前工作，并接受两份相互独立的新颖性风险审查；审查意见一致也不能证明原创性。
- 每个已确认的筛选、阅读和推理阶段都会生成带版本的 Markdown/JSON 报告，并保存证据摘要与恢复状态。
- 新增长周期认知任务需要明确的证据缺口或实质变化；系统优先复用来源，并按预算安排小批次工作，避免重复循环。
- 许可允许时，每年核查 JCR、CCF 和中科院来源状态。单刊 JCR 分区需要相应授权数据；中科院分区在停止更新后仅作历史参考。排名提示不能代替科学判断。
- 内部提示和报告使用简洁英语，原文引文保留原语言，最终面向研究者的报告使用中文。

## 输出目录（生成在用户工作区）

```text
output/
├── discovery_preflight/                    # 候选记录、检索审计、开放获取状态
├── batch/                                  # S1/S2 与冻结的精读任务
├── native/                                 # 签名原生代理任务与回执
└── research_cognition/
    ├── research_memory.sqlite3            # 有证据支持的记忆与决策
    ├── round_reports/INDEX.md             # 轮次报告与完整性清单
    ├── venue_authority/                   # 按年度记录的官方来源核查
    └── research_discovery_package/        # 研究空白、相近工作与实验计划
```

研究数据、全文 PDF、API 密钥、用户的 `goal.md`、本地设置和模型输出默认不属于源代码仓库，并由 Git 忽略规则排除。

## 兼容性与费用

这是独立社区维护的 **Codex Desktop 项目 Skill**，不是 OpenAI 产品、托管 AI 服务或 Codex CLI 封装。`.toml` 代理配置使用原作者的模型命名示例；其他账号可能需要修改模型标识与推理强度。安装器不会检查账号权限。请参阅[原生模型配置](docs/MODEL_PROFILES.md)。项目不保证固定的费用或周使用量；本地预算统计任务数和字符数，不代表服务端订阅额度。

## 开发、来源与许可

离线测试命令、架构说明、限制和发布清单见英文 README 及对应文档。测试使用受控样例，**不能证明**真实模型彼此独立、论文结论正确或实验有效。完整测试需要可选的 PyMuPDF 来生成并检查合成 PDF；生产环境文本解析可回退到 `pypdf`。

本仓库整合了此前开发的文献阅读、发现和研究规划组件，受 [Google Research Harness²](https://github.com/google-research/harness2) 启发，但不包含也不声称包含其代码。

本项目代码采用 **MIT License**，以仓库中的 [LICENSE](LICENSE) 为准。第三方软件包、数据集、论文 PDF、出版方元数据和模型服务各自受其条款约束；另见[来源说明](NOTICE.md)和[依赖许可](docs/DEPENDENCIES.md)。

---

<a id="english"></a>
# search2discovery

**Evidence-first, topic-to-research-plan workflow for Codex Desktop**


**Version 1.0.0** · Python 3.11+ · Windows Codex Desktop · Research planning, **not** experiment execution

Give the system a research topic. It helps find scholarly literature, retrieve legally available full texts, run structured multi-agent paper reviews, challenge apparent research gaps, and prepare **falsifiable research questions, candidate methods, and experiment plans** for a human researcher.

> **What it does not do:** It does not run training, experiments, numerical simulations, GPU jobs, or tests of proposed methods. It cannot guarantee paper novelty, scientific correctness, publisher rankings, model availability, or autonomous execution of paid Codex agents.

## Runtime corrections (runtime.2)

Topic-driven campaigns should converge on **one primary research route and a concrete method**, with explicit candidate rejections. The final method card includes the baseline/model, dataset, information boundary, representation, update operator, objective, supervision, evaluation protocol, resource estimate and kill criteria. An evidence-backed no-viable-method conclusion is valid; novelty is never guaranteed.

- Current-request routing distinguishes full discovery, focused refinement and compare-only work without deep reading.
- New topics enable six-source discovery: arXiv, CVF, PMLR, OpenReview, Crossref and OpenAlex, with cached resumable requests and provider failover. Coverage and lawful full-text availability remain source-dependent.
- OpenAlex distinguishes rate throttling, daily exhaustion and unknown HTTP 429; bounded backoff and persistent cooldowns preserve progress without key rotation.
- Unicode character accounting is consistent across preparation and submission. Historical over-reservations remain conservative; duplicate collection/commit revalidates signed receipts.
- Ready admitted core reading takes priority over optional breadth. Two zero-gain batches against the same evidence gap trigger strategy review.
- `campaign-plan` exposes phase feasibility before further screening. Local caps do not report account quota. Fresh cognition defaults admit all nine required specialist assignments; existing caps are preserved.
- CI compiles and runs regression suites on Windows and Ubuntu with Python 3.11 and 3.12.

### Bootstrap from a personal installation

Install all four sibling Skills in the same personal Skill directory. The public Skill bundles its installer and 27 profiles, so a new workspace does not require the original repository checkout:

```powershell
$python = 'D:\anaconda\python.exe' # Replace with your Python 3.11+ environment.
$skills = Join-Path $HOME '.codex/skills'
& $python (Join-Path $skills 'search2discovery/scripts/bootstrap.py') --project 'D:\ResearchWorkspace'
```

Use `--upgrade` to replace differing installed code with backups; unfinished signed tasks block upgrades. Invoke `$search2discovery` in the project and supply the topic, constraints and budget. During an authorized campaign the lead must dispatch, wait for, collect and commit genuine native threads, then resume. A bounded Python pause is not completion of the research task.

Run `<python> <suite> campaign-plan --workspace <workspace>` before expanding screening. New campaigns require committed `research_discovery_package/route_selection.json` and `final_route_and_method.md`. Structural validation and software tests do not establish scientific truth, originality or experimental gains.


## Workflow

```text
Research topic + constraints
          |
          v
Official venue-source status (annual cache) + topic interpretation
          |
          v
Literature discovery (CORE / RELATED / INSPIRATION candidates)
          |
          v
Legal OA full-text retrieval and S1/S2 screening
          |
          v
R1–R5 independent, original-paper reading + final veto review
          |
          v
Verified evidence ledger / round reports / SQLite research memory
          |
          v
Cross-paper comparison -> contradictions -> candidate hypotheses
          |                          ^
          +--- question-driven prior-art search ---+
          |
          v
Two independent novelty-risk reviews + experiment design
          |
          v
Chinese research recommendations and *unexecuted* experiment plans
```

### Included components

| Component | Purpose |
| --- | --- |
| `paper-discovery-preflight/` | Six-source metadata, deduplication, lawful open-access retrieval, broad interdisciplinary discovery |
| `batch-paper-deepread-desktop/` | S1/S2 screening and five different full-text reading rounds with independent review |
| `research-cognition-engine/` | Research memory, research-question search, contradictions, hypothesis assessment, evidence-aware scheduling and reports |
| `search2discovery/` | **One public Skill entry point**, `$search2discovery` |
| `.codex/agents/` | 27 **configurations** for native Codex Desktop subagents; not 27 simultaneous agents |

Internal engines retain their historical versioned interfaces to protect existing research data and test coverage; the **public release version is v1.0.0**.

## Quick start (Windows PowerShell)

**Prerequisites:** Python **3.11+**, a compatible Codex Desktop app with project-level Skills and native agents, and access to your chosen models. For PDF text extraction, install `pypdf` (BSD-3-Clause):

```powershell
py -3 -m pip install "pypdf>=4"
```

Optional PDF image rendering may require PyMuPDF (`fitz`), which is distributed under **AGPL-3.0 or a commercial license**. Review its terms before using it; it is **not vendored** with search2discovery. See [Dependencies and licensing](docs/DEPENDENCIES.md).

Clone/download the repository, then install into a research workspace:

```powershell
py -3 install.py --project "D:\ResearchWorkspace"
```

For a pre-existing v6.x installation, first back up your workspace and finish outstanding signed native tasks, then:

```powershell
py -3 install.py --project "D:\ResearchWorkspace" --upgrade
```

Open `D:\ResearchWorkspace` in **Codex Desktop**. In its chat, start with:

```text
Use $search2discovery. My research topic is: [YOUR TOPIC].
Work from authentic sources. You may search academic metadata and download
legally accessible open-access PDFs. Keep the topic/approved methods frozen;
use S1/S2 and R1–R5 for admitted core papers; preserve independent checks.
Produce stage reports, defend research gaps against nearest prior art, and
finish with a Chinese report of research questions, candidate methods and
unexecuted experiment plans. Do NOT run experiments, training, or simulations.
Respect the local budget and resume verified checkpoints instead of repeating work.
```

**Important:** Codex Desktop must dispatch real native-agent threads at its agent boundaries; local Python tools cannot independently invoke your subscription's models. A fresh project may require reviewing and committing a model-generated English topic brief before searches proceed. The workflow can pause for legitimate permissions, source gaps, reviewer tasks, or quota limits; it is **not a one-command unattended daemon**.

## Inspect progress without model calls

From the installed project directory:

```powershell
$ws = (Get-Location).Path
$s = Join-Path $ws '.agents\skills\research-cognition-engine\scripts\suite.py'
py -3 $s doctor --workspace $ws
py -3 $s topic-next --workspace $ws
py -3 $s round-reports --workspace $ws
py -3 $s smart-next --workspace $ws
py -3 $s official-status --workspace $ws
```

For full command sequences and permission gates, see [Operations](docs/OPERATIONS.md).

## Evidence and quality rules

- The default bibliography **targets** 50 core + 150 related + 50 cross-disciplinary **distinct candidate records**; these are **targets, not guaranteed retrieval results** and not 250 deep reads.
- S1/S2 screening precedes five required different original-text reading rounds for **admitted core papers**. R3 analyzes authors' **published experimental results** and clearly marked **unexecuted thought experiments** only.
- A DOI/metadata match is not full-text evidence; a page-matched quotation is not independent verification of its interpretation.
- Important hypotheses undergo nearest-prior-art retrieval and two genuinely independent novelty-risk reviews. **Agreement does not prove originality.**
- Each committed screening/reading/reasoning stage gets a versioned Markdown and JSON report; evidence digests and resumption state are retained.
- New long-running cognition cycles require an identifiable evidence gap or meaningful change; the system prefers source reuse and budget-aware small batches over repetitive loops.
- Official JCR, CCF, and CAS publication status is checked annually when permitted. **Individual JCR quartiles require appropriately licensed data**, and the CAS journal partition scheme is a historical reference after its discontinuation. Ranking hints never replace scientific assessment.
- Internal prompts and reports use concise **English**; exact source quotations retain their original language; the final researcher-facing output is **Chinese**.

## Outputs (generated in your workspace)

```text
output/
├── discovery_preflight/                    # Candidate records, query audit, OA retrieval status
├── batch/                                  # S1/S2 and frozen deep-read campaigns
├── native/                                 # Signed native-agent tasks and receipts
└── research_cognition/
    ├── research_memory.sqlite3            # Evidence-backed memory and decisions
    ├── round_reports/INDEX.md             # Per-round reports and integrity manifest
    ├── venue_authority/                   # Per-year official-source check records
    └── research_discovery_package/        # Gap, nearest-work and experiment-plan outputs
```

Research data, full-text PDFs, API keys, user `goal.md`, local settings and model output are **not part of the source repository** and are ignored by Git by default.

## Compatibility and costs

This is an independent, community-authored **Codex Desktop project Skill**, not an OpenAI product, hosted AI service, or Codex CLI wrapper. The `.toml` agent profiles are **examples** tied to the original author's model naming; your account may require changing model identifiers and reasoning efforts. The installer does not validate account entitlements. See [Native model profiles](docs/MODEL_PROFILES.md) for adapting the 27 shipped role configurations. No fixed monetary or weekly usage amount is guaranteed; the local budget counts tasks and characters, not server-side subscription usage.

## Development and provenance

Run the offline suites from the repository root:

```powershell
py -3 -m unittest discover -s batch-paper-deepread-desktop/tests -q
py -3 -m unittest discover -s paper-discovery-preflight/tests -q
py -3 -m unittest discover -s research-cognition-engine/tests -q
py -3 -m unittest tests_original_merge -q
py -3 -m unittest discover -s tests -q
```

These tests use controlled fixtures and **do not** establish real model independence, original paper correctness, or experimental validity. Full test coverage requires optional PyMuPDF to create and inspect synthetic PDF fixtures (the CI workflow installs it for tests only); production text parsing can fall back to `pypdf`. See [Architecture](docs/ARCHITECTURE.md), [Known limitations](docs/LIMITATIONS.md), and [Release checklist](docs/RELEASE_CHECKLIST.md).

This repository consolidates previously developed reading/discovery/research-planning components; it is **inspired by**, but does not embed or claim to be, [Google Research Harness²](https://github.com/google-research/harness2).

## License

**MIT** for code owned by the project maintainers, subject to the [LICENSE](LICENSE) and rights verification before publication. Third-party packages, datasets, PDF papers, publisher metadata and model services are governed by **their own terms**. See [NOTICE](NOTICE.md) and [Dependencies](docs/DEPENDENCIES.md).
