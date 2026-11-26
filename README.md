# Antigravity Codex Subagent

[简体中文](README.zh-CN.md)

Ask Gemini in Antigravity CLI or IDE to work with Codex on a local Windows project. You can read Codex's progress, give it a new instruction while it's working, and pick up the same conversation after restarting Antigravity. Gemini sends each message through the official Python Codex SDK.

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

   The installer creates a private Python environment, installs the pinned SDK, and copies the skill and agent files into `%USERPROFILE%\.gemini\config`. It prints `Installation verified.` after the runner successfully queries local session history.

3. Open a new Antigravity conversation in this repository to load the skill.

## Try a read-only task

Ask Gemini:

> Use Codex to inspect this repository in read-only mode. Name the session test-guide. Which file tests live steering, and how do I run it?

Codex should identify `tests/test_steering.py`. Once it replies, ask “What does that test check before it sends the extra instruction?” Gemini sends the follow-up to the same thread. To authorize changes, say what Codex may edit. You can also specify a model and reasoning effort in your request.

## Monitor, steer, or resume a task

| When | What to say to Gemini | What to expect |
| --- | --- | --- |
| A task is running | “What is Codex doing? Show me the latest test output.” | Gemini reads the original background task's log. It can see public messages, commands, output, exit status, and changed file paths. |
| You want to redirect ongoing work | “Also check what happens if the turn finishes before the message arrives.” | `steer` delivers the instruction to the active turn. An `accepted` receipt confirms delivery. The final answer comes from the original task. |
| The turn has finished | “Continue test-guide and explain how it handles an expired turn ID.” | `resume` starts the next turn in the same Codex thread. |
| You reopened Antigravity or switched between CLI and IDE | “List my Codex sessions, then continue test-guide.” | Gemini looks up the saved thread and its working directory. |

For ongoing chat, say “I want to talk to Codex.” Say “Back to Gemini” to end forwarding. When switching clients, use the same Windows user, Codex home (`CODEX_HOME` if set), and original project directory or worktree.

## Maintain the installation

Run these commands from your clone in PowerShell.

| Task | Command | Result |
| --- | --- | --- |
| Update the skill | `python manage.py update` | Pulls the latest commit with `--ff-only`, installs it, and verifies the installation. Open a new Antigravity conversation to load the changes. |
| Check the installation | `python manage.py check` | Checks the installed files and queries local history. An empty session list is valid. |
| Run the integration test | `python manage.py test` | Runs the repository's test with the installed SDK, a temporary Codex home, and a local mock model. A passing run ends with `OK`. |

## Troubleshoot a session

- **The skill is missing.** Run `python manage.py check` from the clone. If files or the SDK environment are missing, run `python manage.py install` and open a new Antigravity conversation.
- **Codex reports that the thread is already running.** Ask Gemini to read the original task's progress. To change its direction, send the instruction to that active turn with `steer`.
- **A steering request finds no active turn.** Check the original task's status. If it finished, use `resume`. If it's still running, use its recorded working directory and the thread and turn IDs from its log.

For exact PowerShell calls, permission modes, and JSON output fields, see the [skill instructions](skills/codex-delegate/SKILL.md). For the optional native Antigravity subagent window, see the [agent definition](agents/codex.md).
