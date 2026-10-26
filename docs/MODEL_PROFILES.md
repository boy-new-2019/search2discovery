# Native Codex Desktop model profiles

The release contains 27 native agent `.toml` files under `.codex/agents/`. Their `model` strings are **the historical author's project aliases**, not verified public API model identifiers and not a claim that every account can access them:

- `gpt-6-luna` — generally lower-cost topic/screening roles.
- `gpt-6.1-sol` — most research, method and evidence specialists.
- `gpt-6-astra` — adversarial and final-audit specialists.

Before dispatching actual agents, open your Codex Desktop model selector/agent configuration, verify which models and reasoning-effort settings exist on your account, and map these profiles to available equivalents in your **installed project**. Review both `.codex/agents/*.toml` and the installed run/team/router configuration because the native receipt checks expect consistent requested model identities. Do not blindly replace model names in already signed or ongoing research tasks; finish those tasks first.

**Quality is role-based rather than brand-based.** The scientific pipeline needs genuinely independent reviewers and strict evidence checks; it does not require all 27 roles to run concurrently. The installer validates TOML structure, not model access. Offline unit tests simulate native-agent receipts and do not establish availability of the named models.

If model aliases or native agent configuration are unsupported by the current Codex Desktop client, stop and report the incompatibility rather than manufacturing separate-agent evidence.
