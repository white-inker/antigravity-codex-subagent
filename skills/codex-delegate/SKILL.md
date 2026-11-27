---
name: codex-delegate
description: Use in Antigravity CLI or IDE on Windows and Linux to delegate to Codex on explicit request, continue an authorized session, steer or stop a turn, or list saved sessions.
---

# Talk to Codex

Use the Python SDK from the current Antigravity agent. A request to list history authorizes only listing. Workspace writes require user authorization for the project and task. Open the native subagent window only on request.

## Pick the launcher

| Launcher | Prefix from setup | Actions |
| --- | --- | --- |
| Read-only | `readOnly` | `list`, read-only `new` and `resume`, controls for read-only turns |
| Workspace-write | `workspaceWrite` | Writable `new` and `resume`, controls for writable turns |

Run `scripts/setup_runtime.py paths` with `python` on Windows or `python3` on Linux. Use the absolute script path relative to the loaded `SKILL.md` and the returned launcher prefix for the current shell. If the runtime is missing, follow the [setup instructions](references/usage.md). Include `--cwd '<project>'` for turns and controls, and to filter history by project. Omit it for all projects.

The launcher needs access to the host Codex store and the live control endpoint. On Windows use `BypassSandbox: true` for the launcher. On Linux follow the host's approval process if the sandbox blocks that access. Use one-time approval for project-installed launchers and writable calls. A standing approval for a global launcher must include both the interpreter and the exact script path.

Use `WaitMsBeforeAsync: 1000` for new and resumed turns and `10000` for other actions. Report the background task ID and known Codex IDs, then yield. Use completion notifications to collect the original task result. Read its log for progress or missing IDs when needed.

## Send and route messages

For a task, preserve the user's instructions and supply any agent context separately. For direct chat, confirm forwarding before starting and advertise `/codex-exit`. Forward messages verbatim and relay the reply in its original language unless the user requests a translation or summary. Exit only on the standalone command `/codex-exit` or an explicit request to return to Antigravity.

Keep direct-chat routing in `<appDataDir>/brain/<conversation-id>/scratch/codex-chat.json` using the host file tools. Read it before routing messages or notifications. After explicit opt-in, record `enabled`, `taskId`, `workingDirectory`, `mode`, `threadId` and `turnId` as they become known. Apply completion notifications only to the matching task ID. On exit set `enabled` to false. Store only routing metadata.

While a turn runs, use the same launcher, canonical directory, and `--thread` and `--turn` IDs with `--action steer`. If the turn ID is missing, inspect the original log once. If it is still unavailable, tell the user their message has not been sent and can be resent when Codex is ready. Once the turn ends, use `--action resume --thread '<threadId>'`. Retry a steer as a resume only if the original task has ended and delivery failed definitively. Use `interrupt` when asked to stop. Confirm the stop on the original task's `interrupted` result and exit 130.

Use `--message 'text'` for short messages. For literal or private input, write a unique UTF-8 scratch file named `codex-message-<32 hex digits>.txt`. Pass its absolute path via `--consume-message-file` under the installed Antigravity profile. The launcher deletes it after Codex accepts the message. If the turn ended before a steer arrived, reuse the same file for the authorized resume. Use `--message-file` for input files to keep.

Read [launcher examples and troubleshooting](references/usage.md) for exact commands, approval migration, recovery, model settings, and result fields.
