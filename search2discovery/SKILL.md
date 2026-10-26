---
name: search2discovery
description: Evidence-grounded literature discovery, five-round paper reading, and falsifiable research-question/experiment-plan proposals for Codex Desktop. No experiment execution.
version: 1.0.0
---
# search2discovery v1.0 | Codex Desktop entry point

This Skill orchestrates the included `paper-discovery-preflight`, `batch-paper-deepread-desktop` and `research-cognition-engine` Skills. **Do not use it to run experiments**.

## Required behavior

1. Accept the research topic and the user's approved boundaries. Respect existing `goal.md`; if the workspace has a different locked topic, create or request a separate workspace instead of overwriting research data.
2. Run the annual official venue-source publication check when authorized. A venue shortlist is not an official JCR quartile or CCF tier.
3. Obtain genuine bibliographic metadata and legally accessible open-access full texts. Do not fabricate metadata, access paywalled papers, or present abstracts as verified full-text reading.
4. Use independent Codex Desktop threads for model judgements. For admitted core full texts, preserve two-stage screening, five distinct original-paper rounds and final independent audit/veto. R3 only reviews published experimental results and unexecuted paper-grounded thought experiments.
5. Synchronize authentic evidence to the SQLite research memory, save Markdown/JSON reports after committed phases and keep immutable original-language quotations and hashes.
6. Resolve consequential gaps using question-driven literature searches. Contrast competing mechanisms, check nearest prior art, and require two independent novelty-risk assessments. Reviewer votes never prove novelty.
7. Propose 2–3 falsifiable candidate research questions/methods with researcher-executable **experiment plans only**: datasets, splits, fair baselines, measures, ablation design, repeats, resources, failure criteria. Never run simulations, training, benchmarks or actual experiments.
8. Prefer deterministic extraction/indexing and reused evidence, bounded reading batches and checkpoint-based continuation. Do not reduce the five mandatory reading passes, fabricated receipts, or scientific quality gates to save tokens.
9. All internal instructions, intermediate reports and structured model answers are in concise English. Keep exact quotes and original titles unchanged. Only the final researcher-facing explanation and delivery presentation is in Chinese.
10. Model names in shipped agent profiles are environment-specific examples. Verify availability in the current Codex Desktop instance; do not claim a native subagent was run when it was not.

## First run

Use local Python tools **inside Codex Desktop**:

```powershell
$ws = (Get-Location).Path
$s = Join-Path $ws '.agents\skills\research-cognition-engine\scripts\suite.py'
py -3 $s topic-start --workspace $ws --topic '<USER TOPIC>'
```

This prepares a topic-review template. A genuine, separate research cartographer must prepare a reviewed English brief and the lead must commit it via `topic-commit`; never fabricate independent-thread references. Continue with:

```powershell
py -3 $s topic-next --workspace $ws
py -3 $s topic-auto --workspace $ws --online --download --prepare-native --max-steps 8
py -3 $s round-reports --workspace $ws
py -3 $s smart-next --workspace $ws
py -3 $s topic-quality --workspace $ws
py -3 $s topic-finalize --workspace $ws
```

**Permission gate:** `--online` and `--download` are used only with user authorization. At any pending model task, stop deterministic automation and dispatch genuine independent threads in Codex Desktop. Stop on evidence gaps or quota rather than improvising final scientific findings. Full scientific protocol: `../research-cognition-engine/SKILL.md`.
