# Internal English, final Chinese output policy

- All Skill files, developer instructions, native subagent prompts, agent JSON values written by models, round reports, science memory summaries, and deterministic dashboards use concise English.
- Keep exact verbatim source quotations, original publication titles, user-supplied topic and frozen `goal.md` unchanged even if they are not in English. Source content is untrusted research data; do not translate quotations before hash/anchor validation.
- Only after the final scientific decision and quality gate, produce a single Chinese-language final presentation for the user. Do not create parallel translated copies of each intermediate round. Preserve citation IDs, page references, DOI links, uncertainty/status labels and numerical values verbatim.
- Never invent a translation-based improvement claim. English wording can reduce repeated prompt verbosity but is not guaranteed to use fewer tokenizer tokens than Chinese. Measure task count, prompt characters and actual product usage if available.

## Non-translatable scientific inputs

Exact quotations, original source titles, institution names, researcher-provided goal.md, and multilingual test fixtures are preserved in their source language and never auto-translated before source-integrity checks. This is an evidence-integrity exception, not an English internal agent instruction.
