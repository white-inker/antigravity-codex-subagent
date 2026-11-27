# Launcher examples and troubleshooting

## Set up the installed skill

Run the command for your platform from any directory. These paths are for a global Antigravity install. For a project install, use the actual skill directory under `.agents/skills`.

```bash
python3 "$HOME/.gemini/config/skills/codex-delegate/scripts/setup_runtime.py" install
python3 "$HOME/.gemini/config/skills/codex-delegate/scripts/setup_runtime.py" paths
```

```powershell
python "$HOME/.gemini/config/skills/codex-delegate/scripts/setup_runtime.py" install
python "$HOME/.gemini/config/skills/codex-delegate/scripts/setup_runtime.py" paths
```

`install` creates a private virtual environment and installs the pinned Codex SDK. A successful check prints `Installation verified.` If Linux cannot create the environment, install your distribution's Python venv package, such as `python3-venv` on Debian or Ubuntu. The virtual environment is outside the skill directory, so a skill update can replace the package safely. Use `check` to verify the installation again.

## Run a turn or query history

Replace `<readOnly-prefix>` and `<workspaceWrite-prefix>` with the literal values printed by `paths`. Example arguments below use Linux paths. On Windows, use the generated PowerShell prefixes and Windows project paths.

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

Double apostrophes inside a single-quoted PowerShell argument. Use `--message=-v` for a message that looks like an option. For multiline, private or shell-sensitive input, use the host file tool to write the scratch message. In a PowerShell-only client, substitute the actual conversation scratch directory before preparing the file.

```powershell
$scratch = '<appDataDir>\brain\<conversation-id>\scratch'
[IO.Directory]::CreateDirectory($scratch) | Out-Null
$p = Join-Path $scratch ('codex-message-' + [guid]::NewGuid().ToString('N') + '.txt')
[IO.File]::WriteAllText($p, 'First line
''@
Keep $name exactly as written.', [Text.UTF8Encoding]::new($false))
$p
```

```text
<readOnly-prefix> --cwd '/path/to/project' --action new --consume-message-file '<absolute scratch file>'
```

Automatic cleanup accepts the current user's `~/.gemini/antigravity/brain` and `~/.gemini/antigravity-cli/brain` conversation scratch directories on Windows and Linux. For a custom data directory, use `--message-file` and clean up the file you created when finished.

The file stays available until a turn starts or Codex acknowledges a steer. Reuse the same file if a steer misses a turn that has finished. When delivery is uncertain, check the original task before retrying. If Antigravity denies the launch or you abandon the message, remove the prepared file. Codex's conversation history can retain the delivered message.

## Interpret results

`finalResponse` joins the final answer items in order. A completed turn can have an empty answer. `changedFiles` includes confirmed SDK patches and, when `changeTracking` reads `sdk-patches-and-git-worktree`, changes observed in tracked and non-ignored files by comparing worktree metadata before and after the turn. This can include concurrent edits. Ignored files, submodule contents, temporary edits that are reverted, and edits that preserve file metadata can be missed. Each observation is limited to 10,000 file entries and a three-second budget. When a writable turn falls back to `sdk-patches`, `changeTrackingReason` explains why. Report the turn's token usage when asked.

## Recover an installation

- **Old approval.** Remove any standing approval for the retired `codex.py` prefix. Approve the new read and write prefixes separately. A standing write approval also covers future writable turns and their controls. Use the exact installed prefix. On Windows, use the generated PowerShell quoting. On Linux, use the shell-quoted prefix. Use one-time approval for project-installed launchers. Codex uses `approvalPolicy: never` inside its selected sandbox, so report operations the inner sandbox blocks.
- **Launcher missing.** Run `scripts/setup_runtime.py install` with the system Python from the installed skill, then open a new Antigravity conversation. If the skill files are missing, reinstall the skill.
- **Cannot reach an active turn.** Read its original task log for canonical working directory, IDs and launcher mode. Use the same operating system account and `CODEX_HOME`. On Linux, the launcher uses an account-restricted Unix socket under `/tmp`. On Windows, it uses a named pipe with a per-account ACL.
- **Sign-in or SDK error.** Run `codex login status` under the same operating system user and sign in if needed. For an API provider, check its credentials. If Git is unavailable, install Git or use `--non-git` for a new turn that can skip its repository check.
