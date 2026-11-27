---
name: codex-delegate
description: Delegate tasks to Codex on explicit request using the official Python SDK. Start, list, resume, steer, or stop local Codex sessions from a shell-capable agent on Windows, Linux, or macOS.
---

# Delegate to Codex

Use this skill when the user explicitly asks for Codex. A request to list history authorizes only listing. Get the user's authorization before making workspace edits. Preserve the user's instructions and mark any extra context you add.

## Choose a launcher

From the directory of this skill, locate `scripts/setup_runtime.py`. Run it by absolute path with `python` on Windows or `python3` on Linux and macOS. The `paths` subcommand prints prefixes for the host shell. If the runtime is missing, follow [setup and troubleshooting](references/usage.md).

| Prefix | Actions |
| --- | --- |
| `readOnly` | `list`, read-only `new` and `resume`, controls for read-only turns |
| `workspaceWrite` | Writable `new` and `resume`, controls for writable turns |

Use the returned prefix with `--cwd '<project>'` for turns and controls. For history, use `list` with `--cwd` to filter by project, or omit it to search across projects. The runner needs access to local Codex state and its control endpoint. Follow the host's terminal and approval rules. Use one-time approval for writable calls and project-installed launchers where available. A standing approval must include the interpreter and exact launcher script.

## Run or continue a turn

Start with `--action new --message '<task>'`. Get the current thread's saved ID, working directory, and mode from its output or from `--action list`. Continue from the same directory with `--action resume --thread '<threadId>'` and the matching launcher.

If the host can launch background tasks, keep the original task handle and tell the user how to ask for progress or stop it. Read the original task's output for the thread ID, turn ID, progress, and final JSON. Use the host's completion notification if available.

For a running turn and a user-requested follow-up, invoke the same launcher with `--action steer --thread '<threadId>' --turn '<turnId>'` and the new message. If the turn ID is unavailable, check the original task once and tell the user to resend when the ID is available. When the task has finished, use `resume`. Retry an undelivered steer only after confirming the original outcome. For a stop request, use `interrupt` with the active IDs and confirm the stop once the original task reports `interrupted`.

For literal or private input, place a UTF-8 file named `codex-message-<32 hex digits>.txt` in a unique subdirectory of the `scratchRoot` printed by `paths`. Pass its absolute path via `--consume-message-file`. It is deleted after acceptance, so reuse it if the turn ended before a steer arrived. Use `--message-file` for input files to keep.

For direct chat, enter only on request and say that `/codex-exit` returns to the host agent. Forward the user's messages verbatim. Relay Codex's reply in its original language unless the user requests translation or a summary. See [direct chat and examples](references/usage.md).
