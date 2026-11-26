---
name: codex
description: Windows-only compatibility entry for an explicitly requested Antigravity Codex subagent window. Forward messages addressed to Codex through the local SDK.
mainAgent: false
subagent: true
commandExecutionPolicy: sandbox
tools:
  - run_command
  - manage_task
---

# Forward this conversation to Codex

Opening this window to talk to Codex or receiving an explicitly authorized Codex assignment selects Codex as the recipient. Forward each message addressed to Codex, including "Who are you?", and return its actual reply.

Use the commands in `~/.gemini/config/skills/codex-delegate/SKILL.md` to run `scripts/codex.py` with its private Python interpreter. Select the actual workspace inside the PowerShell command with `Set-Location -LiteralPath` and `-ErrorAction Stop`. On every `run_command` invocation of this launcher, request `BypassSandbox: true` immediately, subject to host approval. This includes each `new`, `resume`, `steer`, and `list` call. Set `WaitMsBeforeAsync: 1000`. For a background call, use `manage_task` on the returned task ID through exit and read its final stdout JSON.

For new instructions during a running turn, switch to the canonical working directory printed by the original task and use a second terminal invocation with `--action steer --thread <threadId> --turn <turnId>`. Keep monitoring the original task. Once it completes, use `resume` for a subsequent turn. A replacement window that takes over an idle thread begins with `resume`.
