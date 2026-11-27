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

If `runtimeStatus` is `inaccessible`, request access through the host before trying again. This result leaves `runtimeExists` unknown. Run installation only when the runtime is missing or its dependencies need repair.

## Run a turn or query history

Replace `<readOnly-prefix>` and `<workspaceWrite-prefix>` with the literal values printed by `paths --shell`. Quote the example arguments for your shell. In cmd, use double quotes around paths and messages.

```text
<readOnly-prefix> --cwd '/path/to/project' --action new --message 'Why does the login test fail?'
<workspaceWrite-prefix> --cwd '/path/to/project' --action new --message 'Fix the login test.'
<readOnly-prefix> --cwd '/path/to/project' --action list --limit 1
```

Use the first result for the latest session. Use its `mode` to select the launcher. If the result is empty and has a `nextCursor`, pass it with `--cursor` and the same filters. `--all` includes general Codex history. `skippedUnreadable` counts older rows whose source lookup failed.

Use the same launcher as the active turn to steer or stop it. Replace the read-only prefix below with the write prefix for a writable turn.

```text
<readOnly-prefix> --cwd '/path/to/project' --action steer --thread '<threadId>' --turn '<turnId>' --message 'Also check expired tokens.'
<readOnly-prefix> --cwd '/path/to/project' --action interrupt --thread '<threadId>' --turn '<turnId>'
<readOnly-prefix> --cwd '/path/to/project' --action resume --thread '<threadId>' --message 'Continue.'
```

`accepted` means the steer reached the turn. `interruptRequested` confirms receipt of the request. Read final stdout JSON from the original task. After a timeout or uncertain delivery, check the original task before retrying.

New sessions use the launcher's mode. Resume uses the recorded mode. To explicitly change it or continue a legacy thread missing its record, use the matching launcher with `--mode read-only` or `--mode workspace-write`. If the first turn failed to start, keep its logged thread ID and retry once the cause is resolved. An unnamed thread gets the recovery name `Retry <threadId>` in that case.

When switching models, the runner omits the old thread's effort unless you pass one. Use `--effort default` to use the configured default even when keeping the same model.

## Preserve literal input

Use `--message=-v` for a message that looks like an option. For multiline, private, or shell-sensitive input, use a UTF-8 file. Create a per-conversation subdirectory under the `scratchRoot` returned by `paths`. Use a generated name such as `codex-message-7caf37f2e1154326aa29257767cb5445.txt`.

```text
<readOnly-prefix> --cwd '/path/to/project' --action new --consume-message-file '<absolute scratch file>'
```

The file stays available until a turn starts or Codex acknowledges a steer. Reuse the same file if a steer misses a turn that has finished. When delivery is uncertain, check the original task before retrying. If the host denies the launch or you abandon the message, remove the prepared file. An empty generated scratch subdirectory is removed after delivery. Codex's conversation history can retain the delivered message.

## Route direct chat

If your host exposes a stable conversation ID and writable conversation state, keep `enabled`, `taskId`, `workingDirectory`, `mode`, `threadId`, and `turnId` there as they become known. Apply task notifications only to the matching task. On `/codex-exit`, set `enabled` to false. Store metadata only. If the host offers no persistent conversation state, recover the thread through history and let the user select it before forwarding after a restart.

## Interpret results

`finalResponse` joins the final answer items in order. A completed turn can have an empty answer. `changedFiles` includes confirmed SDK patches and, when `changeTracking` reads `sdk-patches-and-git-worktree`, changes observed in tracked and non-ignored files by comparing worktree metadata before and after the turn. This can include concurrent edits. Ignored files, submodule contents, temporary edits that are reverted, and edits that preserve file metadata can be missed. Each observation is limited to 10,000 file entries and a three-second budget. When a writable turn falls back to `sdk-patches`, `changeTrackingReason` explains why. Report the turn's token usage when asked.

## Recover an installation

- **Old approval.** Remove any standing approval for the retired `codex.py` prefix. Approve the new read and write prefixes separately. A standing write approval also covers future writable turns and their controls. Use the generated prefix for your shell and one-time approval for project-installed launchers. Codex uses `approvalPolicy: never` inside its selected sandbox, so report operations the inner sandbox blocks.
- **Files left after an in-place upgrade.** Use `scripts/setup_runtime.py install --clean-legacy` to remove the old `scripts/.venv` and `steering_linux.py` after the external runtime passes its check. The old environment's locally installed packages are removed with it.
- **Launcher missing.** Run `scripts/setup_runtime.py install` with the system Python from the installed skill, then reload or restart the host conversation. If the skill files are missing, reinstall the skill.
- **Cannot reach an active turn.** Read its original task log for canonical working directory, IDs and launcher mode. Use the same operating system account and `CODEX_HOME`. On Linux and macOS, the launcher uses an account-restricted Unix socket under `/tmp`. On Windows, it uses a named pipe with a per-account ACL.
- **Sign-in or SDK error.** Run `codex login status` under the same operating system user and sign in if needed. For an API provider, check its credentials. If Git is unavailable, install Git or use `--non-git` for a new turn that can skip its repository check.
