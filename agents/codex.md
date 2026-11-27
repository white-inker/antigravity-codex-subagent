---
name: codex
description: Windows and Linux compatibility entry for an explicitly requested Antigravity Codex subagent window. Forward messages addressed to Codex through the local SDK.
mainAgent: false
subagent: true
commandExecutionPolicy: sandbox
tools:
  - run_command
  - manage_task
  - view_file
  - write_file
---

# Forward this conversation to Codex

Use the installed `~/.gemini/config/skills/codex-delegate/SKILL.md` for the read-only and write launcher prefixes, approval scope, and session rules. Forward messages addressed to Codex and return its actual reply. Announce entry into direct chat and acknowledge exit requests locally.

During direct chat, use the skill's stored routing state and its rules for `steer`, `resume`, and `/codex-exit`.

For `new` and `resume`, use a 1000 ms initial wait. For `list`, `steer`, and `interrupt`, use 10000 ms. When a turn becomes a background task, report the known IDs and yield to the user. Use the platform's completion notification to collect the result. Read the running log on a progress request or to obtain IDs needed for an active control. For a stop request, send `interrupt` and confirm the stop when the original task reports `interrupted` with exit 130.
