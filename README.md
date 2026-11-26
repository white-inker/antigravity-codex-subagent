# Antigravity Codex Subagent

[简体中文](README.zh-CN.md)

Ask the Antigravity agent in the CLI or IDE to work with Codex on a local Windows project. You can read Codex's progress, give it a new instruction while it's working, and pick up the same conversation after restarting Antigravity. The agent sends each message through the official Python Codex SDK.

## Before you start

- Install Antigravity CLI or IDE on Windows.
- Make sure `git --version` and `python --version` work in PowerShell. Use Python 3.10 or later.
- Set up Codex authentication for the Windows user who runs Antigravity. If you already use the Codex CLI, run `codex login status` to check your sign-in. [Codex authentication](https://developers.openai.com/codex/auth)

## Install the skill

1. In PowerShell, clone the repository and open its directory.

   ```powershell
   git clone https://github.com/white-inker/antigravity-codex-subagent.git
   Set-Location -LiteralPath .\antigravity-codex-subagent -ErrorAction Stop
   ```

2. Run the installer. If you edited a previous installation's skill or agent files, save your changes first.

   ```powershell
   python manage.py install
   ```

   The installer creates a private Python environment, installs the pinned SDK, and writes the fixed launcher prefix for your profile into the installed skill. It installs the skill and agent files into `%USERPROFILE%\.gemini\config`. It prints `Installation verified.` after the runner successfully queries local session history.

3. Open a new Antigravity conversation in this repository to load the skill.

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

For ongoing chat, say “I want to talk to Codex.” You can send another message before Codex replies. The agent forwards it to the running turn with `steer`. If the turn ID is still unavailable, the agent tells you the message is pending and keeps it for delivery. Once the turn finishes, follow-ups use `resume` on the same thread. Say “come back” to exit direct chat and cancel unsent messages.

The agent reports the available IDs when a task starts in the background and relays the result on Antigravity's completion notification. Direct chat preserves the language of each message and reply. Ask explicitly for a translation or summary. For a delegated task, the agent can supply relevant context separately from your instructions. When switching clients, use the same Windows user, Codex home (`CODEX_HOME` if set), and original project directory or worktree.

## Reuse workspace permissions

New sessions default to read-only. Authorize edits for a task to start it in workspace-write mode. The runner saves this choice when it creates the thread. If the first turn fails to start, fix the cause and retry with the thread ID from the original task. `resume` inherits the saved mode. An explicit mode change becomes the new default for that thread once the resumed turn starts. Older threads without a recorded mode require an explicit choice once. Steering keeps the active turn's settings.

The final result includes a deduplicated `changedFiles` list from completed Codex patch events. Renames include the old and new paths. Inspect the workspace separately for changes made by shell commands or partial failures. An interrupt requests a graceful stop and leaves already-applied changes in place.

## Maintain the installation

Run these commands from your clone in PowerShell.

| Task | Command | Result |
| --- | --- | --- |
| Update the skill | `python manage.py update` | Pulls the latest commit with `--ff-only`, installs it, and verifies the installation. Open a new Antigravity conversation to load the changes. |
| Check the installation | `python manage.py check` | Checks the installed files and queries local history. An empty session list is valid. |
| Run the integration test | `python manage.py test` | Runs the repository's test with the installed SDK, a temporary Codex home, and a local mock model. A passing run ends with `OK`. |

## Troubleshoot a session

- **The skill or its Python environment is missing.** Follow [Install the skill](#install-the-skill) to obtain the repository and run `python manage.py install` in the directory containing `manage.py`. The installed interpreter is `%USERPROFILE%\.gemini\config\skills\codex-delegate\scripts\.venv\Scripts\python.exe`. Run `python manage.py check` from the same directory and look for `Installation verified.`.
- **The latest session is missing.** Use `--action list --workspace '.' --limit 1` and take the first match. Filtered searches scan 20 candidates per page, up to 100 per call. The last page can contain extra matches. If the result is empty and has a `nextCursor`, keep the filters and pass that cursor to continue.
- **Codex reports that the thread is already running.** The follow-up is still pending. The agent can read the original task's IDs and deliver it with `steer`.
- **A steering request finds no active turn.** Check the original task's status. If it finished, use `resume`. If it's still running, switch to the canonical directory printed as `[codex] Working directory:` and use the thread and turn IDs from the same log. A subdirectory identifies a different pipe.

- **Codex needs sign-in.** Run `codex login status` and, if signed out, `codex login` under the same Windows account. For an API provider, check its credentials. `manage.py check` verifies local history access.
- **Git is missing.** Install Git for Windows and confirm `git --version` works, or use `--non-git` to start without the repository check.
- **The provider rejects a model or effort.** Check the reported model and effort. When you change the model, specify an effort it supports to override the inherited value.

Before its first launcher call in a conversation, the agent explains what “Always allow” covers. It skips the notice if it already knows a previous call to the same launcher ran without a prompt. A standing approval for the installed interpreter **and** this runner can allow future messages and `workspace-write` calls without another prompt. You can choose a one-time approval instead. Codex uses `approvalPolicy: never` inside the turn and reports operations that need elevated permissions.

For exact PowerShell calls, UTF-8 file input, history pagination, and JSON output fields, see the [skill instructions](skills/codex-delegate/SKILL.md). For the optional native Antigravity subagent window, see the [agent definition](agents/codex.md).
