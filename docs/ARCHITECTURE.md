# Architecture

search2discovery v1.0.0 is a Codex Desktop multi-Skill **research-planning** workflow. The data flow is:

1. **Topic interpretation:** user constraints are frozen; independent research cartographer prepares a reviewed query contract.
2. **Annual source status:** cached official JCR/CCF/CAS publication checks; journal- or conference-specific ranks remain unverified absent authorized direct evidence.
3. **Discovery:** authentic bibliographic records; three disjoint target pools (50/150/50) with recent/related/cross-disciplinary coverage. OA PDF acquisition only where lawful and available.
4. **S1/S2 screening:** question-level and mechanism-level screening with signed independent Codex tasks.
5. **R1–R5 core reading:** five mandatory different original-text passes: problem, mechanism, published evidence/desk scenarios, adversarial limitations, and synthesis; independent audits and veto.
6. **Research evidence store:** source hashes, page-anchored citations, SQLite knowledge/contradictions/questions, and per-round Markdown/JSON provenance.
7. **Research reasoning:** MAP, MECHANISM, CONTRADICTION, HYPOTHESIS, NOVELTY, EXPERIMENT (design only), FINAL; question-driven prior-art retrieval and dual novelty-risk reviewers.
8. **Result:** a Chinese research proposal with alternative methods, closest prior art, and an unexecuted experimental blueprint. The researcher performs empirical work externally.

A deterministic local Python scheduler prepares/checks/reuses tasks. Real model subagents are invoked by the Codex Desktop lead, not by Python in an unattended daemon. A constrained ranking-strategy proposer may be tested offline and adopted only with independent review. Scientific claims do **not** self-validate through repeated agent consensus.

**Persistent state:** Workspace-local `goal.md`, `input/`, `cross_domain_input/`, `output/`, JSON config and SQLite database. These are excluded from Git. The release ZIP contains source and example configurations only.

**Internal directories:** The three historical Skill directories retain their names so old checkpoint references remain valid. The public entrypoint is `.agents/skills/search2discovery/SKILL.md` after installation.
