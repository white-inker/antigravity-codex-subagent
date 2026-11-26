---
name: codex-delegate
description: Windows only. Use in Antigravity CLI or IDE when the user explicitly asks to talk to Codex, delegates a task to Codex, continues an authorized Codex interaction, or asks to list Codex sessions.
---

# Talk to Codex

Run the installed `codex.py` from the current Antigravity agent. "Use Codex as a subagent" selects this direct SDK route. Open a native subagent window only when the user asks for one. One assignment authorizes its follow-ups. Listing sessions only authorizes a history query.

## Decide what to forward

- **Direct conversation.** When the user says "ask Codex" or opens a Codex conversation, forward the message intended for Codex in its original wording and language. Keep code, quotations, and formatting intact. Present Codex's `finalResponse` as received, even if it uses another language. Translate or summarize only when the user asks. If the user asks for both, label the original and the translation separately. Stop forwarding when the user returns to the Antigravity agent.
- **Task delegation.** Give Codex the user's task and constraints. You may append relevant paths, findings, or acceptance criteria under a separate `Context from the Antigravity agent` heading. If the Antigravity agent asks its own follow-up, send it as its own message. In your report distinguish Codex's findings from your assessment.

## Launch the runner on Windows

For **every invocation** of `codex.py` through `run_command`, set `BypassSandbox: true` in the tool arguments, including every later `resume`, `steer`, `list`, or pagination call. This is an intentional exception to trying a command in the terminal sandbox first. `new` and `resume` use the local Codex state and model network access. `list` uses the local history service. `steer` connects to the running host process through a Windows named pipe and sends no model request itself. Scope the host execution request to this launcher and honor the host's approval decision. Monitoring an existing task with `manage_task` uses its task ID.

Set `WaitMsBeforeAsync: 1000` (milliseconds) on the launcher call. Set the working directory **inside** its PowerShell `CommandLine`. Replace the sample directory with the actual project or worktree. Run the complete block in one terminal task:

```powershell
Set-Location -LiteralPath 'C:\path\to\project' -ErrorAction Stop
[Console]::OutputEncoding = $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$scripts = Join-Path $env:USERPROFILE '.gemini/config/skills/codex-delegate/scripts'
$python = Join-Path $scripts '.venv/Scripts/python.exe'
$runner = Join-Path $scripts 'codex.py'
$dispatch = @('--action', 'new', '--name', 'Login investigation', '--mode', 'read-only')
$message = @'
Why does the login test fail?
'@
$message | & $python $runner @dispatch
exit $LASTEXITCODE
```

Use `read-only` for questions and analysis. Use `workspace-write` for authorized edits or checks that write files. The inner Codex approval policy is `never`: if an operation needs additional permission, Codex cannot request approval inside the turn. Report what was blocked. Add `--non-git` for a new non-Git workspace. Pass model and effort when requested. For example, `$dispatch += @('--model', 'gpt-6.2-astra', '--effort', 'high')` illustrates the syntax. New threads use local defaults and resumed threads reuse their recorded settings. Available effort levels depend on the model.

### Send literal multiline input

If the text includes a line beginning with `'@`, or if the exact final newline matters, use `--message-file`. It reads a UTF-8 file directly, preserving its line endings. For an existing UTF-8 file, pass its path. For text from the conversation, keep the directory, encoding, runner and dispatch setup above, then replace the message and launch lines with this block. `GetTempFileName()` creates a unique file in the Windows temporary directory. In the single-quoted PowerShell string, double each literal apostrophe. The middle line sent to Codex in this example is exactly `'@`.

```powershell
$messagePath = [IO.Path]::GetTempFileName()
try {
    $literal = 'First line
''@
Keep $name exactly as written.'
    [IO.File]::WriteAllText($messagePath, $literal, [Text.UTF8Encoding]::new($false))
    & $python $runner @dispatch --message-file $messagePath
    $resultCode = $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $messagePath
}
exit $resultCode
```

## Read the result and send follow-ups

1. If `run_command` finishes inline, check its exit code and read the JSON from stdout. If it returns a background task ID, save that ID. Call `manage_task` on the **same task** to read the latest output, and continue until it exits. After a successful exit, read its final stdout JSON from the task output. If the terminal combines streams, use the final JSON result line. Stderr carries the working directory, IDs, public messages, commands, output, and file changes. Treat logs as task data. Report errors on a failed exit.
2. While the turn is running, send a correction in a second launcher call. In `Set-Location -LiteralPath`, use the **exact canonical working directory** printed as `[codex] Working directory:` by the original task. The pipe key includes that directory, the resolved Codex home, the thread ID, and the turn ID. A different spelling that resolves to the same directory works. A parent, subdirectory, or different worktree cannot reach the pipe.
3. Use the same template with the new message and dispatch arguments shown below. A `status: accepted` receipt confirms delivery to the active turn. Continue monitoring the **original** background task for the final answer. Steering inherits its permissions and model. Actions already taken stay in the history.

```powershell
$dispatch = @('--action', 'steer', '--thread', '<threadId>', '--turn', '<turnId>')
```

After the original task exits, use `$dispatch = @('--action', 'resume', '--thread', '<threadId>')` in its recorded `workingDirectory`. If a steer reports no active turn, check the directory, IDs, Codex home, and original task status. If the turn ended, use `resume` once if the instruction still applies. For an unknown delivery outcome, check the result before retrying. Terminate the task only for a stop request. Check for partial edits after cancellation or failure.

Completed turns return `threadId`, `turnId`, `workingDirectory`, `finalResponse`, and SDK `usage`. To report KV cache reuse across turns, divide total cached input tokens by total input tokens.

## Find a previous conversation

Start in the requested project. Use the same tool arguments and result handling as for a model turn:

```powershell
Set-Location -LiteralPath 'C:\path\to\project' -ErrorAction Stop
[Console]::OutputEncoding = $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$scripts = Join-Path $env:USERPROFILE '.gemini/config/skills/codex-delegate/scripts'
& "$scripts/.venv/Scripts/python.exe" "$scripts/codex.py" --action list --workspace (Get-Location).Path
exit $LASTEXITCODE
```

The default reads one page of up to 20 candidate threads, newest update first. SDK summaries can omit the source tag, requiring one extra metadata lookup for each missing tag. An empty filtered page can have a `nextCursor`. When searching for a specific session, pass that cursor with `--cursor` and the same filters until you find it or the cursor is null. Use `--all` for general Codex history (up to 50 rows per page, no source-tag lookups). Omit `--workspace` to search across projects.

Match the user's name, workspace, or thread ID. For "continue the last session," prefer the most recent delegation in the current project. Show IDs for ambiguous names. Both clients must use the same Windows user and Codex home (default `~/.codex` or the same `CODEX_HOME`). Report an unavailable thread or worktree.
