# Execution and recovery

This document complements the public Skill; consult the sibling cognition Skill for full CLI and evidence schemas.

## Bounded loop

1. Inspect `topic-next` and signed pending manifests. Reuse completed receipts before preparing anything new.
2. Run authorized deterministic actions with `topic-auto`. It may stop after one network/download batch intentionally.
3. For a prepared native task, read its dispatch, profile and exact prompt. Start the requested real independent thread with the required available model settings, wait, collect with the actual thread reference and commit. Do not fabricate thread references or manually advance stages.
4. Repeat until a final positive plan, independently reviewed no-viable conclusion, explicit user budget/time boundary or a concrete external blocker. Requesting a broad campaign does not require per-batch confirmation.
5. At a blocker save the current stage, evidence already obtained, pending actions, local-cap vs provider-limit distinction and resume command. Do not count a wait or keyword index as scientific progress.

Useful commands (`<suite>` is the installed cognition `scripts/suite.py`):

```text
<python> <suite> campaign-plan --workspace <ws>
<python> <suite> topic-next --workspace <ws>
<python> <suite> topic-auto --workspace <ws> --online --download --prepare-native --max-steps 8
<python> <suite> round-reports --workspace <ws>
<python> <suite> topic-quality --workspace <ws>
<python> <suite> topic-finalize --workspace <ws>
```

New topic commit enables multi-source routing. Existing campaigns can opt in additively:

```text
<python> <installed paper-discovery-preflight/scripts/multisource.py> configure --workspace <ws>
<python> <installed paper-discovery-preflight/scripts/multisource.py> run --workspace <ws> --online --max-requests 12 --max-steps 24
<python> <installed paper-discovery-preflight/scripts/multisource.py> status --workspace <ws>
```

Budgets are local admission ceilings, not an OpenAI account reading. `campaign-plan` reports estimated remaining reader work and reserves nine cognition specialist assignments in the plan; it does not change caps or reserve actual provider spend. Estimates can overcount completed core work and omit contingencies. Existing Pro5x presets may deliberately allow only a short session; they cannot promise a complete campaign within one cap.

OpenAlex persists cached responses, physical-request accounting and typed pauses. Per-second/unknown 429 uses bounded backoff and Retry-After; daily exhaustion pauses that account until a checkpoint allows a later probe. Neither reaching a guessed reset time nor adding a key proves restored allowance. Healthy independent providers can continue.

After independently committed screening, use `gap-record --workspace <ws> --event-file <json>` to append a target-gap observation; `gap-status --workspace <ws>` inspects it. The event contains batch_id, gap_id, strategy, effective_gain (integer or null), gain_basis=COMMITTED_INDEPENDENT_SCREENING_TARGET_GAP and artifacts=[{path,sha256}], including the real commit.json. Effective gain must refer to qualified evidence for that specific gap, not download counts. Re-submitting a different observation for the same batch/gap is rejected.

## Final delivery

Provide `research_landscape.md`, a paper/mechanism comparison, gaps, candidate dispositions, novelty assessment, experiment blueprint, concrete `final_route_and_method.md` / `route_selection.json`, and a Chinese final report plus execution summary. Existing filenames from legacy campaigns remain usable. The final recommendation must cite real work/source identities, distinguish proposed from source-reported methods, and name unresolved semantic and empirical questions. No-viable output records why every candidate failed and the smallest discriminating next evidence; it is not a fabricated positive result.
