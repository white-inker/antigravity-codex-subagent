# Codex Delegate

[简体中文](README.zh-CN.md)

Use the same Agent Skill to delegate local work to Codex from a host with terminal access. The skill uses the official Python SDK on Windows, Linux, and macOS. It can start a thread, report progress, steer or stop an active turn, and resume it later.

## Install the skill

1. Run the following command and select your agent. Add `--global` for a user-wide install, or `--agent <name>` to select an agent directly.

   ```text
   npx skills add white-inker/codex-subagent --skill codex-delegate
   ```

   If the installer lacks a target for your host, copy the whole `skills/codex-delegate` directory into the host's skill directory. [Skills CLI](https://github.com/vercel-labs/skills) · [Agent Skills format](https://agentskills.io/specification)

2. Open a terminal in the installed skill directory. Use Python 3.10 or later with `venv`. On Debian or Ubuntu, you may need the `python3-venv` package.

   ```bash
   python3 scripts/setup_runtime.py install
   ```

   On Windows, run `python scripts/setup_runtime.py install`. Setup installs the pinned SDK and prints `Installation verified.` after reading local history. It keeps the environment outside the skill folder.

3. Sign in to Codex under the operating system account that runs your agent. If you already use the Codex CLI, run `codex login status`. Reload the host's skills, then ask it to use Codex for a task. [Codex authentication](https://developers.openai.com/codex/auth)

## Try a read-only task

Ask your agent:

> Use Codex to inspect this repository in read-only mode. Name the session test-guide. Which file tests live steering, and how do I run it?

Codex should identify `tests/test_steering.py`. Once it replies, ask “What does that test check before it sends the extra instruction?” The agent sends the follow-up to the same thread. To authorize changes, say what Codex may edit. You can also specify a model and reasoning effort in your request.

## Monitor, steer, or resume a task

| When | What to say to your agent | What to expect |
| --- | --- | --- |
| A task is running | “What is Codex doing? Show me the latest test output.” | The agent reads the original background task's log. It can see public messages, commands, output, exit status, and changed file paths. |
| You want to stop the current task | “Stop that Codex turn.” | The agent requests a stop. When the original turn reports `interrupted` (exit 130), the agent confirms it stopped and reports any confirmed patch paths. |
| You want to redirect ongoing work | “Also check what happens if the turn finishes before the message arrives.” | `steer` delivers the instruction to the active turn. An `accepted` receipt confirms delivery. The final answer comes from the original task. |
| The turn has finished | “Continue test-guide and explain how it handles an expired turn ID.” | `resume` starts the next turn in the same Codex thread. |
| You reopened the host or changed clients | “List my Codex sessions, then continue test-guide.” | The agent looks up the saved thread and its working directory. |

For ongoing chat, say “I want to talk to Codex.” Once the turn ID is available, the agent forwards new messages to the running turn with `steer`. During startup, the agent tells you if it needs you to resend a message later. After completion, follow-ups use `resume` on the same thread. Enter `/codex-exit` to return to your agent.

The agent reports the available IDs when a task starts in the background and relays the result when the background task completes. Direct chat preserves the language of each message and reply. Ask explicitly for a translation or summary. For a delegated task, the agent can supply relevant context separately from your instructions. When switching clients, use the same operating system user, Codex home (`CODEX_HOME` if set), and original project directory or worktree.

## Reuse workspace permissions

New sessions default to read-only. Authorize edits for a task to start it in workspace-write mode. The runner saves this choice when it creates the thread. If the first turn fails to start, fix the cause and retry with the thread ID from the original task. `resume` inherits the saved mode. An explicit mode change becomes the new default for that thread once the resumed turn starts. Older threads without a recorded mode require an explicit choice once. Steering keeps the active turn's settings.

The final result includes confirmed SDK patches in `changedFiles`. Writable Git turns also include observed file additions, edits and removals, including shell changes to tracked and non-ignored files. The `changeTracking` field identifies coverage. An interrupt requests a graceful stop and leaves already-applied changes in place.

## Maintain the installation

For a Skills CLI installation, run `npx skills update codex-delegate --global` and run the installed runtime setup again after updating. For a project installation, use `--project` in place of `--global`.

Run the following commands from a repository checkout. On Linux, use `python3`.

| Task | Command | Result |
| --- | --- | --- |
| Update the skill | `python manage.py update` | Pulls the latest commit with `--ff-only` and refreshes the runtime for the checkout. Reload the host's skills to load the changes. |
| Check the installation | `python manage.py check` | Checks the runtime and queries local history. An empty session list is valid. |
| Run the integration test | `python manage.py test` | Runs the repository's test with the installed SDK, a temporary Codex home, and a local mock model. A passing run ends with `OK`. |

## Troubleshoot a session

- **The skill or its Python environment is missing.** Follow [Install the skill](#install-the-skill). To check the runtime again, run the installed `scripts/setup_runtime.py` with `check` and look for `Installation verified.`.
- **The latest session is missing.** Use `--action list --cwd '<project>' --limit 1` and take the first match. If the result is empty and has a `nextCursor`, keep the filters and pass that cursor to continue.
- **Codex reports that the thread is already running.** The follow-up is still pending. The agent can read the original task's IDs and deliver it with `steer`.
- **A steering request finds no active turn.** Check the original task's status. If it finished, use `resume`. If it's still running, switch to the canonical directory printed as `[codex] Working directory:` and use the thread and turn IDs from the same log. A subdirectory identifies a different pipe.

- **Codex needs sign-in.** Run `codex login status` and, if signed out, `codex login` under the same operating system account. For an API provider, check its credentials. `manage.py check` verifies local history access.
- **Git is missing.** Install Git and confirm `git --version` works, or use `--non-git` to start without the repository check.
- **The provider rejects a model or effort.** Check the reported values. Changing models uses the configured default unless you set an effort. Use `--effort default` to reset effort for the current model.

The read-only and write launchers have separate approval prefixes that each include the interpreter and script path. Use one-time approval for writable calls to review them individually. When upgrading, remove standing approvals for the retired `codex.py` launcher. Live controls use a named pipe on Windows and a Unix socket on Linux. The endpoint is restricted to the operating system account that owns the turn.

For launcher commands, UTF-8 file input, and JSON output fields, see the [launcher reference](skills/codex-delegate/references/usage.md).
