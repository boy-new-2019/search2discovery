# Two-stage screening and five-round source reading

S1: identify the scientific problem and source-backed relevance, retain uncertainty. S2: independently assess method transfer, related evidence and misclassification risk. Choose and freeze the core after both rounds; metadata-only records do not count as read papers.

R1: research problem, contributions and assumptions (original fulltext).
R2: model mechanism, math definitions, equations and reproducibility requirements (original fulltext).
**R3: experiments *reported in published papers* only: datasets, splits, baselines, evaluation metrics, ablations, statistical claims, compute costs, confounding. Allow labeled qualitative `HYPOTHETICAL_NOT_EXECUTED` counterfactual desk reasoning, never an actual/virtual simulation run or an invented numerical result.**
R4: strongest skeptical counterargument, protocol comparability and critical weaknesses.
R5: integrate cross-paper evidence, unresolved scientific questions and potentially transferable mechanisms.

Every round rereads all admitted core fulltext chunks, stores page-anchored quotations and explicitly flags unavailable images/tables/formulas for visual review. The final independent method and evidence audit must pass with no valid veto. Original citation strings are preserved in source language; analytic instructions and internal round reports use English. See RCE `references/R3_PAPER_ONLY_PROTOCOL_V66.md`.
