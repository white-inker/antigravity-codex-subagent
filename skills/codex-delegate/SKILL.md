---
name: codex-delegate
description: Windows only. Use in Antigravity CLI or IDE to talk to Codex on explicit request, continue an authorized delegation, steer or interrupt an active turn, or list saved sessions.
---

# Talk to Codex

Use the installed Python SDK runner from the current Antigravity agent. An explicit delegation authorizes that task and its follow-ups. A history query only authorizes listing sessions. Open a native subagent window only on request.

**Direct chat.** When the user asks to enter Codex chat, confirm in their language: "Your next messages will go to Codex. Say 'come back' to return." Forward the intended message verbatim, including greetings and code. Return Codex's actual answer in its original language, unless the user asks for a translation or summary. Treat "come back", "回来", or an equivalent exit instruction as local: confirm "You're back with the Antigravity agent" and end forwarding.

**Delegated task.** Preserve the user's instructions. You may append relevant paths, findings, and acceptance criteria under a separate `Context from the Antigravity agent` heading. Distinguish your own follow-ups and assessment from Codex's reply.

## Launch from any directory

The installer fills in the **literal interpreter and script paths** in the examples below. Copy that exact, two-path prefix into a single PowerShell `CommandLine` on every call. Replace the example project, IDs, and message with real values. Pass the project through `--cwd`. Keep assignments, pipelines, directory changes and extra commands out of the launcher invocation.

| Action | `WaitMsBeforeAsync` | Input |
| --- | ---: | --- |
| `new`, `resume` | 1000 | `--message` or `--message-file` |
| `steer` | 10000 | Same message options plus the active IDs |
| `list`, `interrupt` | 10000 | No message |

On **every** `run_command` invocation of this launcher, set `BypassSandbox: true` at submission. This overrides sandbox-first probing for the runner. Model turns use the network, history uses the host Codex store, and live controls use a host named pipe. Follow Antigravity's permission decision. If the host offers a standing approval, the user may approve the prefix covering **both** the interpreter and this specific `codex.py` path. Keep that prefix stable. Host policy determines the prompts. Leave approval rules under the user's control.

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action new --name 'Login investigation' --mode read-only --message 'Why does the login test fail?'
```

Use single-quoted PowerShell literals for short messages; double a literal apostrophe. For multiline input, quotes that the shell may reinterpret, private text, or exact final newlines, write the intended text using the host's literal text-file facility to a unique UTF-8 file in the Windows temporary directory. An existing UTF-8 file can be passed directly. Supply its absolute path in the same single-command form. Clean up a temporary file you created once the launcher has read it or the task has exited.

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action new --name 'Review' --message-file 'C:\path\to\message.txt'
```

For a PowerShell-only client, create the file in a separate preparation step. This example writes three lines, preserving a line beginning with `'@` and a literal `$name`. Use the printed path in `--message-file`.

```powershell
$p = [IO.Path]::GetTempFileName()
[IO.File]::WriteAllText($p, 'First line
''@
Keep $name exactly as written.', [Text.UTF8Encoding]::new($false))
$p
```

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

`interruptRequested` acknowledges the request. The original task reports its terminal status (normally `interrupted`, exit 130). If it finished first, use its actual outcome. Completed edits can remain on disk. Reserve forced termination for an explicitly requested hard stop or an unresponsive task after informing the user. If delivery is unknown, inspect the original outcome before retrying.

After the turn exits, send the next message using its thread ID:

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action resume --thread '<threadId>' --message 'Continue the earlier task.'
```

New threads default to `read-only`. Use `workspace-write` for authorized edits or checks that write files. Resume inherits the last mode recorded by this runner. Pass `--mode read-only` to narrow access. For threads without a saved mode (including older installations), choose an explicit mode from the current authorization on the first resume. Model and effort also carry forward. When changing models, select a supported effort when necessary. Example syntax: `--model gpt-6.2-astra --effort high`. Live controls use the active turn's settings. Codex's inner approval policy is `never`; report operations blocked by permissions.

The final JSON includes `status`, `finalResponse`, `changedFiles`, IDs, working directory, model, effort and mode. `changedFiles` lists unique paths from completed SDK patches, including both paths of a move. Shell writes and partially applied failures can require inspecting the workspace. Failed turns return a nonzero exit code and an error. Report token usage only when asked.

## List and recover sessions

```powershell
__CODEX_LAUNCHER__ --cwd 'C:\path\to\project' --action list --workspace '.' --limit 20
```

The runner scans automatically until it finds the requested number of matches or reaches the end, five SDK pages, or 100 candidates. Default target: 20 delegated threads. `--limit` accepts 1 through 50. The result includes `scanned` and a `nextCursor` if more history is available. Continue with the same filters and `--cursor` only if the user needs further results. `--all` returns one page of general Codex history without per-thread source checks. Omit `--workspace` to search across projects.

For "continue the last session," use the most recent delegation for the current project. When names overlap, show IDs and workspaces. Preserve the user's selection if the original thread or worktree is unavailable.

## First-use troubleshooting

- **Missing private Python or SDK.** From the repository clone run `python manage.py install`, then `python manage.py check`. Open a new Antigravity conversation to load the installed skill.
- **Sign-in or provider authentication failure.** For a Codex account, run `codex login status` and, if signed out, `codex login` as the same Windows user. For a configured API provider, check its credentials. A successful local history check verifies installation only.
- **Git missing.** Install Git for Windows and make `git --version` available, or use `--non-git` for a new session when a Git check is unnecessary.
- **Unsupported model or effort.** Report the provider error and the model/effort pair from the runner. If the inherited effort is incompatible with a new model, pass both flags explicitly on the next authorized attempt.
