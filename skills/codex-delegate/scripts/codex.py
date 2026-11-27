"""Host-independent launchers for the official Codex SDK."""
import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from openai_codex import CodexConfig, CodexError, Sandbox, Thread
from openai_codex.client import CodexClient
from openai_codex.generated.v2_all import ReasoningEffort
from pydantic import ValidationError

from setup_runtime import scratch_root
from steering import identifier
from workspace import git_executable, workspace_changes, workspace_snapshot

if sys.platform == "win32":
    from steering_windows import control_turn, own_thread, steering_endpoint
elif sys.platform in ("linux", "darwin"):
    from steering_unix import control_turn, own_thread, steering_endpoint
else:
    raise SystemExit("The Codex delegation skill supports Windows, Linux, and macOS.")

SOURCE = "codex-delegate"
DELEGATION_SOURCES = {SOURCE, "antigravity"}
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                "output_tokens", "reasoning_output_tokens")


def arguments(launcher_mode):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("new", "resume", "steer", "interrupt", "list"))
    parser.add_argument("--thread", help="Codex thread ID")
    parser.add_argument("--turn", help="Expected active turn ID for steer or interrupt")
    parser.add_argument("--cwd", type=Path, help="Run in this project or the recorded worktree")
    parser.add_argument("--workspace", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--name")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--message", help="Message to send directly")
    inputs.add_argument("--message-file", type=Path, help="Read the exact message from a UTF-8 file")
    inputs.add_argument("--consume-message-file", type=Path, help="Read and delete a generated scratch message")
    parser.add_argument("--mode", choices=("read-only", "workspace-write"))
    parser.add_argument("--model")
    parser.add_argument("--effort", choices=["default", *(e.value for e in ReasoningEffort)],
                        help="Use the selected model's configured default or set an explicit effort")
    parser.add_argument("--non-git", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--cursor")
    parser.add_argument("--limit", type=int, metavar="1..50",
                        help="Target matches; delegated history includes all matches on the last page")
    args = parser.parse_args()
    args.launcher_mode = launcher_mode
    if args.model is not None:
        args.model = args.model.strip()
        if not args.model:
            parser.error("--model requires a Codex model ID")
    args.action = args.action or ("resume" if args.thread else "new")
    if args.action in ("list", "interrupt") and any(
            value is not None for value in (args.message, args.message_file, args.consume_message_file)):
        parser.error("message options are for new, resume, or steer")
    if args.mode and args.mode != launcher_mode:
        parser.error(f"{launcher_mode} launcher cannot use --mode {args.mode}")
    if args.action == "list" and launcher_mode != "read-only":
        parser.error("use codex_ro.py to list history")
    if args.limit is not None and (args.action != "list" or not 1 <= args.limit <= 50):
        parser.error("--limit is for list and must be between 1 and 50")
    if args.action in ("resume", "steer", "interrupt") and not args.thread:
        parser.error("resume, steer and interrupt require --thread")
    if args.action == "new" and args.thread:
        parser.error("new requires a fresh thread")
    if (args.action in ("steer", "interrupt")) != bool(args.turn):
        parser.error("steer and interrupt require --turn; other actions do not take it")
    if args.action in ("steer", "interrupt") and any((args.mode, args.model, args.effort, args.non_git, args.name)):
        parser.error("active turn controls cannot change turn settings")
    return args


def list_sessions(client, args):
    with ThreadPoolExecutor(max_workers=8) as lookups:
        return scan_history(client, args, lookups)


def scan_history(client, args, lookups):
    sessions = []
    target = args.limit or (50 if args.all else 20)
    scanned = 0
    skipped = 0
    cursor = args.cursor
    params = {"sourceKinds": ["exec", "appServer", "cli", "vscode", "unknown"] if args.all
              else ["exec", "vscode", "appServer"], "sortKey": "updated_at",
              "modelProviders": []}
    workspace = args.workspace
    if getattr(args, "cwd", None) is not None:
        workspace = args.cwd / workspace if workspace is not None else args.cwd
    if workspace:
        params["cwd"] = str(workspace.resolve(strict=True))

    unreadable = object()

    def legacy_source(thread_id):
        try:
            return client.thread_read(thread_id, include_turns=False).thread.thread_source
        except (CodexError, ValidationError):
            return unreadable

    for _ in range(5):
        # The cursor points past the whole page, so return all its matches.
        page = client.thread_list(dict(params, limit=target if args.all else 20,
                                       cursor=cursor)).model_dump(mode="json", by_alias=True)
        scanned += len(page["data"])
        modes = {row["id"]: recorded_mode(row["id"]) for row in page["data"]}
        if not args.all:
            legacy_ids = [row["id"] for row in page["data"] if row.get("threadSource") is None
                          and not modes[row["id"]]]
            legacy_sources = dict(zip(legacy_ids, lookups.map(legacy_source, legacy_ids)))
        for row in page["data"]:
            if not args.all:
                source = row.get("threadSource")
                if source is None:
                    source = legacy_sources.get(row["id"], SOURCE)
                if source is unreadable:
                    skipped += 1
                if source not in DELEGATION_SOURCES:
                    continue
            sessions.append({
                "threadId": row["id"], "name": row.get("name") or (row.get("preview") or "")[:72] or row["id"],
                "workingDirectory": row["cwd"],
                "updatedAt": datetime.fromtimestamp(row["updatedAt"], timezone.utc).isoformat(),
                "mode": modes[row["id"]],
            })
        cursor = page.get("nextCursor")
        if args.all or not cursor or len(sessions) >= target:
            break
    result = {"sessions": sessions, "nextCursor": cursor, "scanned": scanned}
    if skipped:
        result["skippedUnreadable"] = skipped
    return result


class TurnLog:
    """Render public SDK output to the background task while stdout stays machine-readable."""

    def __init__(self):
        self.active_item = None
        self.streamed = set()

    def chunk(self, item_id, label, text):
        if not text:
            return
        if self.active_item != item_id:
            self.line(f"{label} ({item_id})")
        self.active_item = item_id
        self.streamed.add(item_id)
        print(text, end="", file=sys.stderr, flush=True)

    def line(self, message):
        prefix = "\n" if self.active_item is not None else ""
        print(f"{prefix}[codex] {message}", file=sys.stderr, flush=True)
        self.active_item = None

    def finish(self, item_id, label, full_text):
        # Some providers send only a completed item. Avoid replaying streamed text.
        if item_id not in self.streamed:
            self.chunk(item_id, label, full_text)
        self.streamed.discard(item_id)
        if self.active_item == item_id:
            print(file=sys.stderr, flush=True)
            self.active_item = None


def collect(turn):
    answers = {}
    changed_files = {}
    log = TurnLog()
    usage = dict.fromkeys(TOKEN_FIELDS, 0)
    baseline = None
    for event in turn.stream():
        payload = event.payload
        if event.method == "thread/tokenUsage/updated":
            counts = payload.token_usage
            total = {field: getattr(counts.total, field) or 0 for field in TOKEN_FIELDS}
            if baseline is None:
                # The first cumulative snapshot already includes the just-finished request.
                baseline = {field: total[field] - (getattr(counts.last, field) or 0) for field in TOKEN_FIELDS}
            usage = {field: total[field] - baseline[field] for field in TOKEN_FIELDS}
        elif event.method == "item/agentMessage/delta":
            log.chunk(payload.item_id, "message", payload.delta)
        elif event.method == "item/commandExecution/outputDelta":
            log.chunk(payload.item_id, "command output", payload.delta)
        elif event.method in ("item/started", "item/completed"):
            item = payload.item.root
            if item.type == "agentMessage" and event.method == "item/completed":
                log.finish(item.id, "message", item.text)
                if item.phase is None or item.phase.value == "final_answer":
                    if item.text.strip():
                        answers[item.id] = item.text
            elif item.type == "commandExecution":
                if event.method == "item/started":
                    log.line(f"command ({item.id}): {item.command}")
                else:
                    log.finish(item.id, "command output", item.aggregated_output)
                    code = f", exit {item.exit_code}" if item.exit_code is not None else ""
                    log.line(f"command ({item.id}): {item.status.value}{code}")
            elif item.type == "fileChange":
                paths = ", ".join(change.path for change in item.changes)
                log.line(f"file change ({item.id}): {item.status.value} {paths}")
                if event.method == "item/completed" and item.status.value == "completed":
                    for change in item.changes:
                        changed_files[change.path] = None
                        if change.kind.root.type == "update" and change.kind.root.move_path:
                            changed_files[change.kind.root.move_path] = None
        elif event.method == "turn/completed":
            status = payload.turn.status.value
            result = {"status": status, "finalResponse": "\n\n".join(answers.values()),
                      "usage": usage, "changedFiles": list(changed_files)}
            if status == "failed":
                error = payload.turn.error
                result["error"] = error.message if error else "Codex turn failed."
                if error and error.additional_details:
                    result["error"] += f" {error.additional_details}"
            return result
    raise RuntimeError("Codex disconnected before completing the turn.")


def mode_file(thread_id):
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return home / "codex-delegate" / "modes" / identifier(thread_id)


def recorded_mode(thread_id):
    path = mode_file(thread_id)
    if not path.is_file():
        path = path.parents[2] / "antigravity-codex" / "modes" / path.name
    try:
        mode = path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return None
    return mode if mode in ("read-only", "workspace-write") else None


def previous_mode(thread_id):
    mode = recorded_mode(thread_id)
    if mode is None:
        raise ValueError("No saved delegation mode for this thread. Resume once with "
                         "--mode read-only or --mode workspace-write according to the current authorization.")
    return mode


def save_mode(thread_id, mode):
    path = mode_file(thread_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = NamedTemporaryFile(dir=path.parent, delete=False)
    tmp = Path(pending.name)
    try:
        with pending:
            pending.write(mode.encode("ascii"))
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def model_error(message, model, effort):
    level = ReasoningEffort(effort).value if effort else "configured default"
    diagnostic = f"{message} (model={model or 'configured default'}, effort={level})"
    reason = message.lower()
    if any(term in reason for term in ("401", "unauthorized", "not logged in")):
        diagnostic += " Check Codex sign-in (codex login status) or the configured provider credentials."
    elif any(term in reason for term in ("effort", "reasoning", "unsupported model", "model_not_found")):
        diagnostic += " Select an available --model and pass an --effort supported by that model."
    return diagnostic


def run_turn(client, args, prompt, cwd, scratch_message=None):
    with ExitStack() as locks:
        params = {"cwd": str(cwd), "approvalPolicy": "never"}
        if args.thread:
            locks.enter_context(own_thread(args.thread))
            previous = client.thread_read(args.thread).thread
            original = Path(previous.cwd.root).resolve(strict=True)
            if original != cwd:
                raise ValueError(f"Resume in the recorded workspace: {original}")
            mode = args.mode or previous_mode(args.thread)
            model = args.model or previous.model
            effort = args.effort
            if effort is None and model == previous.model:
                effort = previous.reasoning_effort
            params["excludeTurns"] = True
        else:
            if not args.non_git:
                git = git_executable()
                if git is None:
                    raise ValueError("Git was not found on PATH. Install Git or use --non-git to skip the Git check.")
                if subprocess.run([git, "rev-parse", "--git-dir"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                    raise ValueError("Use --non-git to start a session outside a Git repository.")
            mode = args.launcher_mode
            model, effort = args.model, args.effort
            params["threadSource"] = SOURCE
        if mode != args.launcher_mode:
            launcher = "codex_rw.py" if mode == "workspace-write" else "codex_ro.py"
            raise ValueError(f"This thread uses {mode}. Use {launcher} or explicitly select --mode {args.launcher_mode}.")
        effort = None if effort == "default" else effort
        if model:
            params["model"] = model
        if effort:
            params["config"] = {"model_reasoning_effort": ReasoningEffort(effort).value}
        params["sandbox"] = mode
        before = workspace_snapshot(cwd) if mode == "workspace-write" else None
        name_warning = None
        thread = None
        try:
            response = client.thread_resume(args.thread, params) if args.thread else client.thread_start(params)
            opened = response.thread.id
            if args.thread and args.thread != opened:
                raise RuntimeError("Codex resumed a different thread.")
            if not args.thread:
                locks.enter_context(own_thread(opened))
                save_mode(opened, mode)
            print(f"[codex] Working directory: {cwd}\n[codex] Thread ID: {opened}\n[codex] Mode: {mode}",
                  file=sys.stderr, flush=True)
            thread = Thread(client, opened)
            if args.name and not args.thread:
                try:
                    thread.set_name(args.name)
                except CodexError as exc:
                    name_warning = f"Could not save session name: {exc}"
                    print(f"[codex] {name_warning}", file=sys.stderr, flush=True)
            model = response.model
            turn = thread.turn(prompt, sandbox=Sandbox(mode), effort=ReasoningEffort(effort) if effort else None)
            remove_delivered_message(scratch_message)
            effort = effort or response.reasoning_effort
        except CodexError as exc:
            diagnostic = model_error(str(exc), model, effort)
            if thread is not None and not args.thread and (not args.name or name_warning):
                # The SDK persists an empty thread when it receives a name.
                try:
                    thread.set_name(args.name or f"Retry {thread.id}")
                except CodexError as save_error:
                    diagnostic += f" Could not save thread {thread.id} for retry: {save_error}"
            raise RuntimeError(diagnostic) from exc
        with steering_endpoint(turn, mode):
            if args.thread and args.mode:
                save_mode(opened, mode)
            print(f"[codex] Turn ID: {turn.id}", file=sys.stderr, flush=True)
            result = collect(turn)
        result.update(workspace_changes(cwd, before, result["changedFiles"]))
        if result["status"] == "failed":
            result["error"] = model_error(result["error"], model, effort)
        if name_warning:
            result["nameWarning"] = name_warning
        return {"threadId": opened, "turnId": turn.id, "workingDirectory": str(cwd), "mode": mode,
                "model": model, "effort": ReasoningEffort(effort).value if effort else None, **result}


def scratch_message_path(path):
    if (not path.is_absolute() or path.is_symlink()
            or not re.fullmatch(r"codex-message-[0-9a-f]{32}\.txt", path.name, re.IGNORECASE)):
        raise ValueError("--consume-message-file requires an absolute path to a generated scratch message.")
    resolved = path.resolve(strict=True)
    home = Path.home().resolve()
    legacy_roots = {home / ".gemini" / app / "brain" for app in ("antigravity", "antigravity-cli")}
    in_skill_scratch = resolved.parent.parent == scratch_root()
    in_legacy_scratch = (resolved.parent.name.casefold() == "scratch"
                         and resolved.parent.parent.parent in legacy_roots)
    if not resolved.is_file() or not (in_skill_scratch or in_legacy_scratch):
        raise ValueError(f"The message must be a regular file under the current user's {scratch_root()}.")
    return resolved


def remove_delivered_message(path):
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            print(f"[codex] Message delivered, but scratch cleanup failed: {error}", file=sys.stderr, flush=True)


def main(launcher_mode):
    args = arguments(launcher_mode)
    scratch_message = None
    if args.cwd is not None and args.action != "list":
        os.chdir(args.cwd)
    cwd = Path.cwd().resolve(strict=True)
    if args.action != "list":
        if args.workspace and args.workspace.resolve(strict=True) != cwd:
            raise ValueError(f"Run this command in {args.workspace}")
        if args.action == "interrupt":
            return control_turn(args.thread, args.turn, args.launcher_mode, "interrupt")
        if args.consume_message_file is not None:
            scratch_message = scratch_message_path(args.consume_message_file)
            prompt = scratch_message.read_bytes().decode("utf-8-sig")
        elif args.message_file is not None:
            prompt = args.message_file.read_bytes().decode("utf-8-sig")
        elif args.message is not None:
            prompt = args.message
        else:
            if sys.stdin.isatty():
                raise ValueError("Pass a message with --message, a message file, or UTF-8 stdin.")
            prompt = sys.stdin.buffer.read().decode("utf-8-sig")
        if not prompt.strip():
            raise ValueError("The message is empty.")
        if args.action == "steer":
            receipt = control_turn(args.thread, args.turn, args.launcher_mode, "steer", prompt)
            if receipt["status"] == "accepted":
                remove_delivered_message(scratch_message)
            return receipt
    with CodexClient(CodexConfig(cwd=str(cwd))) as client:
        client.initialize()
        if args.action == "list":
            return list_sessions(client, args)
        return run_turn(client, args, prompt, cwd, scratch_message)


def cli(launcher_mode):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        result = main(launcher_mode)
        if result.get("status") == "failed":
            print(f"Codex delegation failed: {result['error']}", file=sys.stderr, flush=True)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result.get("status") == "failed":
            sys.exit(1)
        if result.get("status") == "interrupted":
            sys.exit(130)
    except (CodexError, OSError, RuntimeError, ValueError) as error:
        sys.exit(f"Codex delegation failed: {error}")


if __name__ == "__main__":
    sys.exit("Use codex_ro.py or codex_rw.py. The old shared launcher has been retired.")
