# search2discovery v1.0.0

Initial public-source release candidate of an evidence-grounded, topic-to-research-plan workflow for Windows Codex Desktop.

## Included

- Topic interpretation, yearly official venue-source status checks and metadata-backed academic discovery.
- Three disjoint literature candidate pools (targets: 50 core, 150 related, 50 interdisciplinary).
- Lawful OA full-text acquisition, S1/S2 selection, five mandatory R1–R5 reading rounds for admitted core papers and independent audit/veto.
- Page-anchored evidence, SQLite research memory, automatic per-round Markdown/JSON reports, and checkpoint-based resumability.
- Contradiction mapping, question-driven prior-art retrieval, two independent novelty-risk reviews and research-method / **unexecuted** experiment-plan recommendations.
- Cost-aware shortlisting and constrained strategy optimization; no actual experiment execution.
- New public `$search2discovery` Skill entrypoint and install alias; historical components retained for compatibility.

## Limitations

Requires a compatible Codex Desktop account with supported native agent functionality. Agent model identifiers are examples. Only offline software tests have been run for this release candidate. OpenAlex/PDF access and publisher ratings may be incomplete or require subscriptions. The project cannot guarantee novel or scientifically correct results. PDF text and published results need original-source checking. The included LICENSE is subject to maintainer ownership review before public push.

Full documentation: [README](README.md), [Known limitations](docs/LIMITATIONS.md), [Release checklist](docs/RELEASE_CHECKLIST.md).
