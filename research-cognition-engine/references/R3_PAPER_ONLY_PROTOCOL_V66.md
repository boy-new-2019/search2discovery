# R3 protocol: published experimental evidence and non-executable scenario reasoning

## Allowed evidence
- Published paper tables and figures, original reported metrics, authors' experimental design, datasets, data splits, baselines, compute, ablations and failure cases. Preserve page, quote, experimental protocol, citation and attribution.
- Desk-based 'what-if' or counterfactual scenarios: narrate conditions, predicted qualitative mechanisms, alternative explanations, and the proposed validation an independent researcher might perform in the future. These are NOT executed, simulated measured results or empirical findings. Mark each one `HYPOTHETICAL_NOT_EXECUTED`, status `inferred` and provide supporting paper sources.
- Comparison of published numbers only for meaningfully aligned tasks, datasets, splits, metrics, seed/reporting policy and hardware/protocol. Otherwise mark `NOT_DIRECTLY_COMPARABLE`.

## Prohibited
- No actual or simulated experiments, no Python-based toy simulation, no benchmark run, no GPU training or evaluation, no synthetic scores or calculated-looking invented improvements, no unsupported significance tests, no self-attributed replication, no experimental output folders.
- No treating hypothetical trajectories, mock datasets or illustrative numeric values as observations. If the user requests to execute a simulation later, route it outside this Skill for fresh explicit approval; this workflow remains design-only.

## Minimum R3 report fields
`paper_id`, `reported_datasets`, `reported_baselines`, `reported_metrics`, `protocol_comparability`, `reported_ablations`, `reported_limitations`, `source_anchors`, `desk_scenarios` (optional; each with `mode=HYPOTHETICAL_NOT_EXECUTED`, assumptions, qualitative prediction, confounders and falsifier), `open_questions`.

A missing paper experiment is `NOT_REPORTED`; an inaccessible figure is `VISUAL_REVIEW_REQUIRED`. A source-matched string is not evidence of mathematical, experimental or semantic correctness. Any serious attribution error must trigger independent audit and may veto completion.
