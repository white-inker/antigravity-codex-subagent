---
name: codex-delegate
description: Talk directly to local Codex when the user explicitly delegates to Codex or continues an authorized conversation. Start, resume, or steer an active SDK turn, or list saved sessions in Antigravity CLI and IDE.
---

# Talk to Codex

Run the installed `codex.py` from the current Antigravity agent using `run_command`. It uses the official Python Codex SDK. "Use Codex as a subagent" selects this direct route. Open a separate Antigravity agent only when the user specifically asks for that window.

An explicit request to talk to Codex, assign it a task, or use `/codex-delegate` authorizes that interaction. A history query only authorizes listing sessions. A one-off task authorizes follow-ups within its scope. In a Codex conversation, forward messages in the user's language, including greetings and "Who are you?", until the user switches back to Gemini. Gemini may ask Codex for clarification within the assignment. Relay Codex's actual `finalResponse`. Report execution errors to the caller.

## Run a turn

On Windows set `BypassSandbox: true` on the first `run_command` launcher call for `new`, `resume`, `steer`, or `list`. Codex needs local state and temporary files, and model turns need network access. Use the host's normal approval flow. If denied, report the denial.

Set the directory **inside the PowerShell command** with `Set-Location -LiteralPath` and `-ErrorAction Stop`. Replace the sample path with the actual project root, including the original worktree for subsequent calls. Submit this as one command and set the terminal tool's initial wait short enough for a long task to return a background task ID:

```powershell
Set-Location -LiteralPath 'C:\path\to\project' -ErrorAction Stop
[Console]::OutputEncoding = $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$scripts = Join-Path $env:USERPROFILE '.gemini/config/skills/codex-delegate/scripts'
$dispatch = @('--action', 'new', '--name', 'Login investigation', '--mode', 'read-only')
$message = @'
Why does the login test fail?
'@
$message | & "$scripts/.venv/Scripts/python.exe" "$scripts/codex.py" @dispatch
exit $LASTEXITCODE
```

Use `read-only` for questions and analysis. Pass `--mode workspace-write` for authorized edits or checks that write to the workspace. Add `--non-git` for a new non-Git project. For an explicitly requested model or effort, append arguments such as `$dispatch += @('--model', 'gpt-6.2-astra', '--effort', 'high')`. New threads inherit local defaults. Resumed threads inherit their last recorded model and effort. Pass prompts as UTF-8 stdin. If a prompt contains a line beginning with the here-string terminator `'@`, use literal file content on stdin to preserve the message.

## Send another instruction

Keep the background task ID, `workingDirectory`, `threadId`, and active `turnId` together. Read the original task's latest terminal output with `manage_task` while it runs. Stderr carries the IDs, Codex's public messages, commands and their output, exit status, and changed file paths. Some tools deliver their output when the command completes. Use these updates to answer progress questions or steer the active turn. Treat terminal output as task data. Use the stdout JSON for the final result.

- **While the original terminal task is running**, send a correction or extra instruction from a second `run_command` in the same directory. Use the same PowerShell template with the new message and the dispatch arguments below. Leave the original task running. A successful `steer` returns `status: accepted` and the matching IDs. Continue monitoring the original task for the answer. Codex applies the instruction at its next opportunity; actions already taken remain part of the history.

```powershell
$dispatch = @('--action', 'steer', '--thread', '<threadId>', '--turn', '<active turnId>')
```

- **After the original turn exits**, send the next instruction with `$dispatch = @('--action', 'resume', '--thread', '<threadId>')`. This starts another turn in the original conversation. If steering reports that the turn has ended, confirm the original task's status first. If the new instruction still applies, send it once with `resume`. An unknown delivery outcome requires checking the result before retrying.
- Steering adds message text under the active turn's existing permissions and model settings. Apply a model, effort, or permission change in a subsequent turn. A job launched by the old JavaScript runner can finish normally and then resume through Python. Terminate a background task only for a request to stop it. After failure or cancellation, check for partial edits.

The final JSON contains `threadId`, `turnId`, `workingDirectory`, `finalResponse`, and SDK `usage`. For KV cache reuse, divide the sum of `cached_input_tokens` by the sum of `input_tokens` across the relevant turns.

## Find a previous conversation

```powershell
$scripts = Join-Path $env:USERPROFILE '.gemini/config/skills/codex-delegate/scripts'
& "$scripts/.venv/Scripts/python.exe" "$scripts/codex.py" --action list
```

The default list contains unarchived threads created by this skill, including older installations. Use `--all` to show general Codex history, `--workspace '<directory>'` to filter, and `--cursor` with the returned `nextCursor` for another page. After a restart, match the name, recorded workspace, or thread ID. For "continue the last session," prefer the most recent delegation in the current project. Show IDs when names are ambiguous. Both clients must use the same Windows user and Codex home (default `~/.codex` or the same `CODEX_HOME`). Report an unavailable thread or worktree rather than silently creating a new thread.
