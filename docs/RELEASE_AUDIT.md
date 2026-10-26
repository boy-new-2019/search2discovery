# search2discovery v1.0.0 — Release readiness audit

**Status: public GitHub repository published under MIT at the maintainer explicit request. Historical-source ownership and redistribution rights remain maintainer assertions and were not independently verified.**

## Basis

Reviewed the actual `Research_Cognition_Engine_v6.6_English_Internal_R3_PaperOnly_Windows_Full.zip` distribution and adapted it for an open-source GitHub repository, retaining the original functional sub-engines and their audit constraints. The public product version is `v1.0.0`; old internal version numbers survive only as compatibility and historical provenance.

## Changes completed

| Finding | Resolution |
| --- | --- |
| No single public brand or entrypoint | Added `$search2discovery`, main README and `VERSION` 1.0.0; kept three tested internal engines. |
| Repeated root-level v6.x installation, integration and release documents | Removed 15 redundant historical root documents; replaced with concise public architecture, operations, limitations, and release docs. |
| Duplicated top-level orchestrator | Replaced `research_suite.py` with a compatibility re-export of the authoritative `suite.py`. |
| No visible open-source governance | Added proposed MIT `LICENSE`, `NOTICE`, `CONTRIBUTING`, `SECURITY`, `.gitignore`, release notes and a release checklist. |
| PDF retrieval/storage indirectly required an AGPL/commercial dependency | Added `pypdf` (BSD-3-Clause) text-extraction fallbacks for downloaded PDF verification and evidence-store import. PyMuPDF remains optional for visual inspection; licensing clearly disclosed. |
| No CI or public release tests | Added GitHub Actions offline suite and five deterministic release, install, rights-boundary/PDF fallback tests. |
| Historical native model aliases may not exist for other accounts | Added model profile adaptation documentation; do not claim all 27 roles can be launched on every subscription. |
| GitHub repository may leak active user workspace data | Added `.gitignore` for inputs/outputs, `goal.md`, PDFs, `.env`, API keys, SQLite, and research artifacts; ran static content scan. |
| Source download parser left a file descriptor open for signature check | Replaced with a managed context; offline fallback test passes. |

## Verification performed

- Adapted v4.4 reading engine: **68/68** offline tests passed.
- v5 literature discovery: **39/39** passed.
- v6 research cognition/scheduler/policies: **118/118** passed.
- Original three-system integration: **8/8** passed.
- New public installer, safety and pypdf fallback tests: **5/5** passed.
- **Total: 238 offline tests passed** in the local verification environment, with both optional PDF readers present.
- Clean install: four Skill entrypoints and 27 native-agent configuration TOMLs installed; repeated installation idempotent.
- Upgrade: real v6.6 installer followed by v1.0.0 `--upgrade` preserved an existing `goal.md`, private source input and history output; prior changed code was backed up.
- Static safety scan found no candidate private keys or 11-digit personal telephone numbers. One fixture email `pass@site.com` was a synthetic test address. This is not a guarantee against every undiscovered secret.
- Source files contain no bundled scholarly PDFs or model credentials. Third-party library code is not copied into the repository.

## Important limitations / manual release blockers

1. **License and ownership — MAINTAINER ASSERTION:** The maintainer explicitly requested publication under MIT. This agent did not independently verify ownership, redistribution rights or copyright accuracy for version-derived/adapted source files. OpenAI-generated text, upstream inspirations, and external contributions still warrant rights review. Optional PyMuPDF is AGPL-3.0/commercial.
2. **Genuine Codex Desktop model tests — NOT RUN:** Native model aliases, separate reviewer-thread identity and model availability cannot be verified by offline Python tests. The maintainer should perform a small real desktop smoke test with only public-domain or appropriately licensed paper content.
3. **Actual scholarly novelty and quality — NOT PROVEN:** Matching page quotes does not validate formulas, figures, metric tables or interpretation. Two independent reviewers cannot prove exhaustive novelty. Final human scientific review is required.
4. **No runtime OS-level experiment sandbox — UNVERIFIED:** Skill policy prohibits experiment execution, but Codex tool permissions must also be configured to prevent accidental code or experiment runs. Only legal OA PDF downloads are permitted.
5. **Tokens/quotas — NOT MEASURED:** 27 installed profiles are not 27 simultaneous workers. Local budgeting is a proxy; no percentage of Codex quota savings is guaranteed.
6. **Publisher rankings — NOT COMPLETE:** Annual version/status checks cannot authenticate subscription-only per-journal JCR quartiles or every CCF item. CAS classification policy is historical after discontinuation.
7. **Generic rare-path diagnostic strings — IMPROVEMENT AREA:** Historical engines still contain some broad English exceptions. These do not remove source or audit gates but make user troubleshooting harder. Add specific exceptions in future releases with regression tests.
8. **No end-to-end live science benchmark — NOT RUN:** The 238 tests are offline software tests. Real literature search quality, policy enforcement, and long-context cost require future controlled field evaluation.

**Publication record:** The maintainer requested a public GitHub repository under MIT; `https://github.com/boy-new-2019/search2discovery` was created and pushed on 2026-10-26. This record does not replace maintainer verification of third-party or historical-source rights.
