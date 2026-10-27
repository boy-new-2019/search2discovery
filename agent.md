# Project agent guidance

- Treat the repository as a research-planning tool. Do not claim it executes experiments or proves scientific novelty.
- Keep research artifacts, credentials, downloaded papers, and workspace outputs out of public commits; preserve the existing `.gitignore` boundaries.
- Preserve the historical engine interfaces and public release version unless a task explicitly changes them.
- For repository work on the maintainer's Windows machine, prefer PowerShell 7. Use `D:\anaconda` for local Python environments when Python is needed.
- Do not use `apply_patch`; edit with available native tools and inspect `git diff` before finishing.
- Before public release, verify the maintainer's rights to distribute adapted historical source under the selected license. Do not claim rights verification without evidence.

- Use the latest user request to select full discovery, focused refinement or compare-only mode; historical pasted instructions remain evidence.
- Preserve user research workspaces while repairing the public tool. Validate Windows/Ubuntu and Python 3.11/3.12 compatibility through the declared CI matrix.
