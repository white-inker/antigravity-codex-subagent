# Antigravity Codex Subagent

[简体中文](README.zh-CN.md)

Ask the Antigravity agent in the CLI or IDE to work with Codex on a local project on Windows or Linux. You can read Codex's progress, give it a new instruction while it's working, and pick up the same conversation after restarting Antigravity. The agent sends each message through the official Python Codex SDK.

## Before you start

- Install Antigravity CLI or IDE, Git, and Python 3.10 or later with `venv`. On Debian or Ubuntu you may need the `python3-venv` package.
- Install Node.js with npm to use `npx`.
- Configure Codex authentication for the operating system user who runs Antigravity. If you use the Codex CLI, run `codex login status`. [Codex authentication](https://developers.openai.com/codex/auth)

## Install the skill

1. Install globally for both Antigravity CLI and IDE.

   ```text
   npx skills add white-inker/antigravity-codex-subagent --skill codex-delegate --agent antigravity --global --copy --yes
   ```

   For a project-only install, run the same command from the project root with `--global` omitted. The skill is installed in `.agents/skills/codex-delegate` within the project. [Skills CLI](https://github.com/vercel-labs/skills) · [Antigravity skill locations](https://antigravity.google/docs/skills)

2. Set up the pinned Python SDK for the global install. For a project install, replace the skill path with its project location.

   **Linux**

   ```bash
   python3 "$HOME/.gemini/config/skills/codex-delegate/scripts/setup_runtime.py" install
   ```

   **Windows PowerShell**

   ```powershell
   python "$HOME/.gemini/config/skills/codex-delegate/scripts/setup_runtime.py" install
   ```

   Setup prints `Installation verified.` after checking local history. The virtual environment lives outside the skill directory so updates can replace the skill files.

3. Open a new Antigravity conversation to load the skill.

For a checkout-based install with the optional native subagent definition, clone this repository and run `python manage.py install` from the checkout on Windows, or `python3 manage.py install` on Linux.

## Try a read-only task

Ask the Antigravity agent:

> Use Codex to inspect this repository in read-only mode. Name the session test-guide. Which file tests live steering, and how do I run it?

Codex should identify `tests/test_steering.py`. Once it replies, ask “What does that test check before it sends the extra instruction?” The agent sends the follow-up to the same thread. To authorize changes, say what Codex may edit. You can also specify a model and reasoning effort in your request.

## Monitor, steer, or resume a task

| When | What to say to the Antigravity agent | What to expect |
| --- | --- | --- |
| A task is running | “What is Codex doing? Show me the latest test output.” | The agent reads the original background task's log. It can see public messages, commands, output, exit status, and changed file paths. |
| You want to stop the current task | “Stop that Codex turn.” | The agent requests a stop. When the original turn reports `interrupted` (exit 130), the agent confirms it stopped and reports any confirmed patch paths. |
| You want to redirect ongoing work | “Also check what happens if the turn finishes before the message arrives.” | `steer` delivers the instruction to the active turn. An `accepted` receipt confirms delivery. The final answer comes from the original task. |
| The turn has finished | “Continue test-guide and explain how it handles an expired turn ID.” | `resume` starts the next turn in the same Codex thread. |
| You reopened Antigravity or switched between CLI and IDE | “List my Codex sessions, then continue test-guide.” | The agent looks up the saved thread and its working directory. |

For ongoing chat, say “I want to talk to Codex.” Once the turn ID is available, the agent forwards new messages to the running turn with `steer`. During startup, the agent tells you if it needs you to resend a message later. After completion, follow-ups use `resume` on the same thread. Enter `/codex-exit` to return to Antigravity.

The agent reports the available IDs when a task starts in the background and relays the result on Antigravity's completion notification. Direct chat preserves the language of each message and reply. Ask explicitly for a translation or summary. For a delegated task, the agent can supply relevant context separately from your instructions. When switching clients, use the same operating system user, Codex home (`CODEX_HOME` if set), and original project directory or worktree.

## Reuse workspace permissions

New sessions default to read-only. Authorize edits for a task to start it in workspace-write mode. The runner saves this choice when it creates the thread. If the first turn fails to start, fix the cause and retry with the thread ID from the original task. `resume` inherits the saved mode. An explicit mode change becomes the new default for that thread once the resumed turn starts. Older threads without a recorded mode require an explicit choice once. Steering keeps the active turn's settings.

The final result includes confirmed SDK patches in `changedFiles`. Writable Git turns also include observed file additions, edits and removals, including shell changes to tracked and non-ignored files. The `changeTracking` field identifies coverage. An interrupt requests a graceful stop and leaves already-applied changes in place.

## Maintain the installation

For a Skills CLI installation, run `npx skills update codex-delegate --global` and run the installed runtime setup again after updating. For a project installation, use `--project` in place of `--global`.

Run the following commands from a repository checkout. On Linux, use `python3`.

| Task | Command | Result |
| --- | --- | --- |
| Update the skill | `python manage.py update` | Pulls the latest commit with `--ff-only`, installs it, and verifies the installation. Open a new Antigravity conversation to load the changes. |
| Check the installation | `python manage.py check` | Checks the installed files and queries local history. An empty session list is valid. |
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

For PowerShell calls, UTF-8 file input, and JSON output fields, see the [launcher reference](skills/codex-delegate/references/usage.md). The [agent definition](agents/codex.md) describes the optional native subagent window.
