# Operations (Windows Codex Desktop)

From the repository root:

```powershell
py -3 install.py --project "D:\ResearchWorkspace"
```

Restart/open the target workspace in Codex Desktop. Use the `$search2discovery` Skill with your topic and permissions.

## Local inspection commands

```powershell
$ws=(Get-Location).Path
$s=Join-Path $ws '.agents\skills\research-cognition-engine\scripts\suite.py'
py -3 $s doctor --workspace $ws
py -3 $s topic-start --workspace $ws --topic 'A precise research topic'
# Independent Codex cartographer prepares a reviewed topic brief before this command:
py -3 $s topic-commit --workspace $ws --file "$ws\output\research_cognition\topic_to_plan\topic_brief_reviewed.json"
py -3 $s topic-next --workspace $ws
# Only after explicitly authorizing network research and OA downloads:
py -3 $s topic-auto --workspace $ws --online --download --prepare-native --max-steps 8
py -3 $s round-reports --workspace $ws
py -3 $s smart-next --workspace $ws
py -3 $s topic-quality --workspace $ws
py -3 $s topic-finalize --workspace $ws
```

Model-dispatch boundaries require authentic independent native-agent responses via the Codex Desktop lead. Do not fabricate task JSON/receipts or use unsigned output. Keep evidence and review reports even when a final plan is blocked.

`--upgrade` backs up replaced Skill code, but does not overwrite goal/papers/research outputs. A pending signed task prevents prompt-policy upgrade. Model names and efforts in `.codex/agents/*.toml` are provided as editable examples; confirm your account supports them. The original models may not be available in other environments.

**Internet policy:** `topic-auto --online --download` is explicitly authorized by the user invoking that request. Some annual venue-check entrypoints can request official HTTPS pages; inspect permission policy before using them. No automatic experiments are permitted.
