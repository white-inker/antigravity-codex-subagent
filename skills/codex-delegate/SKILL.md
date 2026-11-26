---
name: codex-delegate
description: Windows only. Use in Antigravity CLI or IDE to talk to Codex on explicit request, continue an authorized delegation, steer or interrupt an active turn, or list saved sessions.
---

# Talk to Codex

Use the installed Python SDK runner from the current Antigravity agent. An explicit delegation authorizes that task and its follow-ups. A history query only authorizes listing sessions. Open a native subagent window only on request.

**Direct chat.** When the user asks to enter Codex chat, confirm in their language: "Your next messages will go to Codex. Say 'come back' to return." Forward the intended message verbatim, including greetings and code. Return Codex's actual answer in its original language, unless the user asks for a translation or summary. Treat "come back", "回来", or an equivalent exit instruction as local: confirm "You're back with the Antigravity agent" and end forwarding.

Before forwarding each new chat message, check the state of the preceding turn:

| Preceding turn | How to deliver the new message |
| --- | --- |
| Running, IDs known | Send the new message once with `steer` to the active thread and turn, even if the message reads like a separate question. |
| Running or starting, turn ID unknown | Read the original task log once for the IDs. If still unavailable, tell the user "Codex is still processing your previous message. This message is pending." Keep the message with the original task ID. |
| Finished | Send the next pending message with `resume` on the same thread. |

On the next task update or user message, handle the oldest pending message first. If a `resume` reports that the thread already has a delegated turn running, its message is still pending. Use the running-turn rule above. If a steer reports no active turn, check the original task. Once it has finished, resume once with the undelivered message. An accepted receipt confirms delivery. If delivery is uncertain, check the outcome before retrying. An exit request ends forwarding and cancels any unsent messages.

**Delegated task.** Preserve the user's instructions. You may append relevant paths, findings, and acceptance criteria under a separate `Context from the Antigravity agent` heading. Distinguish your own follow-ups and assessment from Codex's reply.

## Launch from any directory

The installer fills in the **literal interpreter and script paths** in the examples below. Copy that exact, two-path prefix into a single PowerShell `CommandLine` on every call. Replace the example project, IDs, and message with real values. Pass the project through `--cwd`. Keep assignments, pipelines, directory changes and extra commands out of the launcher invocation.

| Action | `WaitMsBeforeAsync` | Input |
| --- | ---: | --- |
| `new`, `resume` | 1000 | `--message` or `--message-file` |
| `steer` | 10000 | Same message options plus the active IDs |
| `list`, `interrupt` | 10000 | No message |

Before submitting the first launcher call in this conversation, tell the user in their language: "If you choose Always allow for this launcher, future messages and workspace-write calls matching this prefix may run without a separate approval prompt." Give this notice once. Skip it if you already know an earlier call to the same launcher ran without a prompt. The prefix covers **both** the interpreter and this specific `codex.py` path. Follow the host's approval decision and the user's authorization for the task.

On **every** `run_command` invocation of this launcher, set `BypassSandbox: true` at submission. This overrides sandbox-first probing for the runner. Model turns use the network, history uses the host Codex store, and live controls use a host named pipe.

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action new --name 'Login investigation' --mode read-only --message 'Why does the login test fail?'
```

Use single-quoted PowerShell literals for short messages and double a literal apostrophe. For an option-like message, put the value in the same argument as the option: `--message=--help` or `--message=-v`.

For multiline input, shell-sensitive quotes, private text, or exact final newlines, use the host's `write_file` or equivalent literal text-file tool. Write UTF-8 to a unique file under the **current conversation's scratch directory**, `<appDataDir>\brain\<conversation-id>\scratch\`. Resolve the actual directory from the current Antigravity conversation, then pass the same absolute filename to the runner. An existing user-supplied file can be passed directly.

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action new --name 'Review' --message-file '<appDataDir>\brain\<conversation-id>\scratch\codex-message-<unique-id>.txt'
```

For a PowerShell-only client, prepare the file separately in the same conversation scratch directory. Substitute the actual scratch directory before running this example. It preserves a line beginning with `'@` and a literal `$name`.

```powershell
$scratch = '<appDataDir>\brain\<conversation-id>\scratch'
[IO.Directory]::CreateDirectory($scratch) | Out-Null
$p = Join-Path $scratch ('codex-message-' + [guid]::NewGuid().ToString('N') + '.txt')
[IO.File]::WriteAllText($p, 'First line
''@
Keep $name exactly as written.', [Text.UTF8Encoding]::new($false))
$p
```

For an inline call, delete your scratch message file when the call exits. For a background call, record the absolute filename with its terminal task ID **before yielding**. On that task's completion notification, delete that exact file, including on failure or interruption. For a steer, associate the file with the steer command that reads it. Only remove files you created for these calls.

## Hand off a background turn

- If the launcher finishes inline, read its exit status and final stdout JSON. If it goes into the background, keep the terminal task ID. Tell the user Codex is running and that they can add an instruction or ask it to stop. Include the thread ID if it is already in the output; if startup is still in progress, give the task ID. **End the current chat turn.** Let the user continue working.
- Antigravity notifies you when the background task ends. Use that notification to report the result. If it lacks the final output, read the completed task once with `manage_task`. While a task is running, consult its log on a progress request or when a requested steer/stop needs IDs that have not yet arrived. Avoid timer-based polling.
- Stderr identifies the canonical working directory, thread ID and active turn ID. It also carries public messages, command output, exit status and patch paths. Read the final JSON from stdout (the final result line in merged logs). An intermediate control receipt belongs to the control command. The outcome of the turn comes from the original task.

## Continue or stop the selected task

Use the original canonical directory with `--cwd`, the same Windows user and Codex home, and the IDs from the original task. A spelling resolving to the same directory works. A subdirectory or another worktree has a different control pipe.

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action steer --thread '<threadId>' --turn '<turnId>' --message 'Also check expired tokens.'
```

`accepted` means the instruction reached the active turn. For a stop request, send a graceful interrupt:

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action interrupt --thread '<threadId>' --turn '<turnId>'
```

`interruptRequested` acknowledges the control request. When the original task's completion notification shows `status: interrupted` and exit 130 after the user's stop request, report "Stopped as requested." This is the expected stop outcome. If the task finished first, report its actual outcome. Completed edits can remain on disk. Reserve forced termination for an explicitly requested hard stop or an unresponsive task after informing the user. If delivery is unknown, inspect the original outcome before retrying.

After the turn exits, send the next message using its thread ID:

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action resume --thread '<threadId>' --message 'Continue the earlier task.'
```

If a new thread printed a thread ID but its first turn failed to start, keep that ID. Once the cause is resolved, retry with `resume` on that thread. The runner saved its initial mode when it created the thread. An unnamed thread gets the recovery name `Retry <threadId>` if its first turn fails to start.

New threads default to `read-only`. Use `workspace-write` for authorized edits or checks that write files. Resume inherits the last mode recorded by this runner. Pass `--mode read-only` to narrow access. For threads without a saved mode (including older installations), choose an explicit mode from the current authorization on the first resume. Model and effort also carry forward. When changing models, select a supported effort when necessary. Example syntax: `--model gpt-6.2-astra --effort high`. Live controls use the active turn's settings. Codex's inner approval policy is `never`; report operations blocked by permissions.

The final JSON includes `status`, `finalResponse`, `changedFiles`, IDs, working directory, model, effort and mode. `changedFiles` lists unique paths from completed SDK patches, including both paths of a move. Shell writes and partially applied failures can require inspecting the workspace. Failed turns return a nonzero exit code and an error. Report token usage only when asked.

## List and recover sessions

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action list --workspace '.' --limit 20
```

The runner reads delegated history in pages of 20 candidates, newest update first. It stops after a page reaches the target, history ends, or five pages have been scanned (up to 100 candidates). `--limit` accepts 1 through 50, default 20. All matches from the last page are returned so the cursor skips none. For the most recent delegation, use `--limit 1` and take the first result. If a search is still empty and `nextCursor` is present, continue with the same filters and `--cursor`. `--all` returns one general-history page limited to the requested count. Omit `--workspace` to search across projects.

For "continue the last session," use the most recent delegation for the current project. When names overlap, show IDs and workspaces. Preserve the user's selection if the original thread or worktree is unavailable.

## First-use troubleshooting

- **Missing private Python or SDK.** Run `__CODEX_MANAGER__ install` followed by `__CODEX_MANAGER__ check`. The installer records the path to this checkout in the installed skill. If it was moved or removed, clone the [project repository](https://github.com/white-inker/antigravity-codex-subagent) and run `python manage.py install` from the directory containing its `manage.py`. Verify that `%USERPROFILE%\.gemini\config\skills\codex-delegate\scripts\.venv\Scripts\python.exe` exists and the check prints `Installation verified.`. Open a new Antigravity conversation.
- **Sign-in or provider authentication failure.** For a Codex account, run `codex login status` and, if signed out, `codex login` as the same Windows user. For a configured API provider, check its credentials. A successful local history check verifies installation only.
- **Git missing.** Install Git for Windows and make `git --version` available, or use `--non-git` for a new session when a Git check is unnecessary.
- **Unsupported model or effort.** Report the provider error and the model/effort pair from the runner. If the inherited effort is incompatible with a new model, pass both flags explicitly on the next authorized attempt.
