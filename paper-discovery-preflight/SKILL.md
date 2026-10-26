---
name: paper-discovery-preflight
version: 5.0.0-english-policy
summary: Authenticated metadata and public PDF discovery with broad, evidence-aware interdisciplinary coverage; no reading-model calls for basic retrieval.
---
# Literature discovery | Preflight

1. Read the user's locked research direction and validated topic-specific search terms. Never silently substitute the previous autonomous-driving preset into a new topic. Chinese-language user topics are interpreted by an independent research agent into accurate English search expressions before commit.
2. Build mutually disjoint bibliographic candidate pools: at least 50 CORE, 150 RELATED and 50 INSPIRATION where real coverage permits. Prefer recent three years and relevant high-level venues, then expand older years only when justified; archive all retrieval queries and release dates. OpenAlex metadata is **not** an independently verified full text or an official journal tier.
3. Interdisciplinary inspiration spans 15 macro families and 93 subfields; require broad coverage, far-domain representation, and caps on single-field concentration. Randomize deterministically only among authentically retrieved comparable candidates. Never invent titles, author identities, DOIs, awards, numerical outcomes or source tiers.
4. With user permission, download only legally accessible public PDFs; enforce HTTPS, public DNS, bounded filesize, PDF signature, readable content and stored SHA256. Missing full text is recorded as a limitation, never used as an excuse for fabricated reading.
5. Track local state, audit and resume. Reuse existing verified metadata and files. Upgrading topic taxonomy must preserve past provenance. Do not trigger paid fulltext-reading agents for all 250 metadata candidates.
6. Internal prompts, explanations, Skill references and intermediate reports must be concise English; source quotations and bibliographic titles are preserved. Only the final user-facing report is presented in Chinese by the Codex lead.
7. Annual official venue authority checks are performed in the RCE preflight, not by inventing JCR quartiles or treating a venue shortlist as official ranking evidence.

Suggested commands (Python executed by Codex Desktop local tool):
```powershell
py -3 .agents\skills\paper-discovery-preflight\scripts\paper_discovery.py --help
py -3 .agents\skills\research-cognition-engine\scripts\suite.py topic-next --workspace .
```
