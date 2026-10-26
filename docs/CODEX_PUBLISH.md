# Publishing with Codex Desktop

Use this repository as the source; do **not** publish a private active research workspace. The application cannot know which GitHub account you intend to use without your authorization.

1. Extract the v1.0 release ZIP into a **clean local folder**; initialize Git and inspect the staged diff before pushing.
2. Review the MIT license/ownership, PyMuPDF optional licensing, and all repository files for personal or confidential data.
3. Run the five offline test groups and test `py -3 install.py --project <fresh-folder>` on Windows. If the current system supports only model aliases different from the bundled TOMLs, adjust your private installed workspace; document this requirement in the README rather than claiming every account is compatible.
4. Create a GitHub repository named `search2discovery`, **public only upon explicit owner authorization**. Do not commit your research `goal.md`, PDFs, downloaded papers, SQLite memory, credentials or generated reports.
5. Push the reviewed source and tag `v1.0.0`; create a release from `RELEASE_NOTES.md`. Do not claim 233 live-science tests; they are offline software fixtures.

Codex Desktop prompt to paste:

```text
Prepare the extracted search2discovery v1.0.0 folder for public GitHub release.
Audit all staged changes and confirm no credentials, private PDFs, user
research files or workspace output. Preserve the three internal research
engines and public $search2discovery entry point. Run the documented offline
unit suites and the Windows clean-install smoke test; report failures.
Check LICENSE, NOTICE and optional PyMuPDF AGPL compatibility and ask me to
confirm rights/licensing and the target GitHub owner/repository before any
public push or release action. After explicit approval, publish the reviewed
repository as search2discovery and tag v1.0.0. Use RELEASE_NOTES.md verbatim
for release notes. Do not claim real experiments or guaranteed AI novelty.
```
