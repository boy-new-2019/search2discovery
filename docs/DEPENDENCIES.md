# Dependency and licensing notes

**Runtime:** Python 3.11+, Windows Codex Desktop with project Skills and native agents; verified model availability is external to this repository.

**PDF text:** `pypdf>=4` is available under the BSD-3-Clause license and is the recommended permissively licensed PDF text reader. Some historical components prefer **PyMuPDF (`fitz`)** when installed. The public-source CI installs it **for synthetic PDF tests only**; it is not included in the release archive. PyMuPDF is **AGPL-3.0 or commercial**, especially relevant for downstream distributions and services. It is optional and not bundled; review the applicable license and your integration obligations. Some PDF visual-review paths require PyMuPDF and should fail or request manual visual review when unavailable rather than marking papers visually checked.

**Scholarly metadata:** OpenAlex public API, subject to provider terms, rate limits, and networking. Downloaded OA PDFs may have separate copyright licenses; neither the repository nor its MIT LICENSE redistributes those PDFs.

**Official ranking data:** JCR may require a paid institutional subscription for journal quartiles; CCF official directory entries are a separate source; CAS journal categorization ceased updates from 2026 as explained in the Skill's annual-source preflight.

**Security:** Store API keys in environment variables, not checked-in files. No real `goal.md`, published PDFs, personal notes, institution credentials, private `.env` files or task-output databases should be committed.

Useful official upstream information: [PyMuPDF licensing](https://pymupdf.io/licensing), [pypdf](https://pypi.org/project/pypdf/), [OpenAlex](https://docs.openalex.org/).
