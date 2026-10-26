# Release checklist: v1.0.0

- [ ] Maintainer confirms ownership of all source files and approves the MIT license.
- [ ] Check `LICENSE`, `NOTICE.md` and optional PyMuPDF (AGPL-3.0/commercial) implications.
- [x] Static-scan the distribution for credentials and personal/contact patterns (not a guarantee; maintainer must recheck before push).
- [x] Ensure `.gitignore` excludes `input/`, `output/`, `goal.md`, `cross_domain_input/`, `.env` and local runtime configs.
- [x] Run all five offline test suites (238 pass with both optional readers installed); separately verify CI after GitHub push.
- [ ] Verify a clean Windows 3.11+ project install from the packaged archive; check both fresh install and `--upgrade` preserving personal state.
- [ ] Review 27 native agent model identifiers and document how a new user substitutes those unsupported by their plan.
- [ ] Test real Codex Desktop native agents with a small **public** research example; check citations, report hashes, and what happens on incomplete full text.
- [ ] Confirm all examples use public sample data, not an unpublished paper or a user-specific working directory.
- [ ] Confirm no self-directed training, real experiment execution, bypassed paywalls, synthetic measurements or invented official venue ratings.
- [ ] Create a repository named `search2discovery`, push only after maintainer review, tag `v1.0.0` and attach the standalone source ZIP.
- [ ] State clearly in the GitHub Release that offline tests do not certify scientific novelty, native-agent access or guaranteed subscription allowance.

See `docs/CODEX_PUBLISH.md` for an executable Codex Desktop publication handoff.
