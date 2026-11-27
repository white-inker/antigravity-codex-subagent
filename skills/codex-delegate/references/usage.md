# Launcher examples and troubleshooting

## Set up the installed skill

Open a terminal in the installed skill directory reported by your installer. Use the same setup and launcher commands for every host.

```bash
python3 scripts/setup_runtime.py install
python3 scripts/setup_runtime.py paths --shell bash
```

```powershell
python scripts/setup_runtime.py install
python scripts/setup_runtime.py paths --shell powershell
```

`install` creates a private virtual environment and installs the pinned Codex SDK. A successful check prints `Installation verified.` If Linux cannot create the environment, install your distribution's Python venv package, such as `python3-venv` on Debian or Ubuntu. The virtual environment is outside the skill directory, so a skill update can replace the package. Use `check` to verify the setup again.

On Windows, pass `--shell bash` for Git Bash or `--shell cmd` for Command Prompt. Plain `paths` also lists the available variants under `shells` in UTF-8 JSON. Parse the JSON and use the values for your shell as written. For paths containing `%` or `!`, use PowerShell or Bash because cmd may expand them.

If `runtimeStatus` is `inaccessible`, `runtimeExists` is unknown. Use the printed prefix for the intended launcher call with approved access. If the call fails, use its error to decide what to check. Run `check` or `install` with the required host access when diagnosing or repairing the runtime. Install only when the runtime is missing or its dependencies need repair.

## Run a turn or query history

Replace `<readOnly-prefix>` and `<workspaceWrite-prefix>` with the literal values printed by `paths --shell`. Quote the example arguments for your shell. In cmd, use double quotes around paths and messages.

```text
<readOnly-prefix> --cwd '/path/to/project' --action new --message 'Why does the login test fail?'
<workspaceWrite-prefix> --cwd '/path/to/project' --action new --message 'Fix the login test.'
<readOnly-prefix> --cwd '/path/to/project' --action list --limit 1
```

Reuse the known thread for related work in the same project. When recovering an earlier thread, filter with `--cwd` and select the session that fits the task. Use the first result when the user asks for the latest session. Use the recorded `mode` and current authorization to select the launcher. If the result is empty and has a `nextCursor`, pass it with `--cursor` and the same filters. `--all` includes general Codex history. `skippedUnreadable` counts older rows whose source lookup failed.

Use the same launcher as the active turn to steer or stop it. Replace the read-only prefix below with the write prefix for a writable turn.

```text
<readOnly-prefix> --cwd '/path/to/project' --action steer --thread '<threadId>' --turn '<turnId>' --message 'Also check expired tokens.'
<readOnly-prefix> --cwd '/path/to/project' --action interrupt --thread '<threadId>' --turn '<turnId>'
<readOnly-prefix> --cwd '/path/to/project' --action resume --thread '<threadId>' --message 'Continue.'
```

`accepted` means the steer reached the turn. `interruptRequested` confirms receipt of the request. Read final stdout JSON from the original task. After a timeout or uncertain delivery, check the original task before retrying.

New sessions use the launcher's mode. Resume uses the recorded mode. To explicitly change it or continue a legacy thread missing its record, use the matching launcher with `--mode read-only` or `--mode workspace-write`. If the first turn failed to start, keep its logged thread ID and retry once the cause is resolved. An unnamed thread gets the recovery name `Retry <threadId>` in that case.

When setting `--model`, prefer an explicit `--effort` supported by that model. Use `--effort default` when the configured default is desired or support for a suitable explicit value is unclear. On resume, omitting `--effort` inherits the saved effort if the model stays the same. A different model uses its configured default unless you pass a supported effort.

## Preserve literal input

Use `--message=-v` for a message that looks like an option. For multiline, private, or shell-sensitive input, use a UTF-8 file. Automatic cleanup accepts regular files named `codex-message-<32 hex digits>.txt` in the runtime's system temp directory, in `scratchRoot`, or in a direct child of either. Existing supported host conversation scratch directories still qualify. Use an owner-only file or directory for sensitive input. Symbolic links and files inside the resolved `--cwd` project directory are excluded from automatic cleanup.

```text
<readOnly-prefix> --cwd '/path/to/project' --action new --consume-message-file '<absolute scratch file>'
```

The file stays available until a turn starts or Codex acknowledges a steer. Reuse the same file if a steer misses a turn that has finished. When delivery is uncertain, check the original task before retrying. If the host denies the launch or you abandon the message, remove the prepared file. An empty child of the skill's scratch directory can be removed after delivery. Codex's conversation history can retain the delivered message.

Use `--message-file` for any readable path, including an arbitrary host scratch directory or an existing project file. The launcher preserves that file. If you created it as temporary input, clean it up after confirming delivery.

## Route direct chat

Treat a standalone “come back”, “回来”, `/codex-exit`, or an explicit request to leave Codex chat as an exit. Forward messages where those words are part of ordinary content. On exit, turn off forwarding and clean up any unsent files you created.

If the turn ID is still unavailable after one log check, save the user's exact follow-up as a UTF-8 scratch file and tell them it is queued. Keep an ordered list of pending file paths with the original task handle. When handling the next task update or user message, process any exit or stop request first, then deliver queued messages in order. Use `steer` if the original turn is active. If it completed, use `resume` on the same thread. Wait for confirmation before sending the next file, and check the original task when delivery is uncertain. Pause the queue if the user stops the turn, and resume delivery when they ask to continue.

When the host exposes writable conversation state, persist `enabled`, `taskId`, `workingDirectory`, `mode`, `threadId`, `turnId`, and the ordered pending file paths there as they become known. Keep message contents in the scratch files. Apply notifications only to the matching task. If the host cannot persist state across a restart, recover the thread through history and let the user select it before forwarding.

## Interpret results

`finalResponse` joins the final answer items in order. A completed turn can have an empty answer. `changedFiles` includes confirmed SDK patches and, when `changeTracking` reads `sdk-patches-and-git-worktree`, changes observed in tracked and non-ignored files by comparing worktree metadata before and after the turn. This can include concurrent edits. Ignored files, submodule contents, temporary edits that are reverted, and edits that preserve file metadata can be missed. Each observation is limited to 10,000 file entries and a three-second budget. When a writable turn falls back to `sdk-patches`, `changeTrackingReason` explains why. Report the turn's token usage when asked.

## Recover an installation

- **Old approval.** Remove any standing approval for the retired `codex.py` prefix. Approve the new read and write prefixes separately. A standing write approval also covers future writable turns and their controls. Use the generated prefix for your shell and one-time approval for project-installed launchers. Codex uses `approvalPolicy: never` inside its selected sandbox, so report operations the inner sandbox blocks.
- **Files left after an in-place upgrade.** Use `scripts/setup_runtime.py install --clean-legacy` to remove the old `scripts/.venv` and `steering_linux.py` after the external runtime passes its check. The old environment's locally installed packages are removed with it.
- **Launcher missing.** Run `scripts/setup_runtime.py install` with the system Python from the installed skill, then reload or restart the host conversation. If the skill files are missing, reinstall the skill.
- **Cannot reach an active turn.** Read its original task log for canonical working directory, IDs and launcher mode. Use the same operating system account and `CODEX_HOME`. On Linux and macOS, the launcher uses an account-restricted Unix socket under `/tmp`. On Windows, it uses a named pipe with a per-account ACL.
- **Sign-in or SDK error.** Run `codex login status` under the same operating system user and sign in if needed. For an API provider, check its credentials. If Git is unavailable, install Git or use `--non-git` for a new turn that can skip its repository check.
