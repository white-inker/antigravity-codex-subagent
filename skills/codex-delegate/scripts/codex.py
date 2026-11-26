"""Antigravity's Windows CLI for the official Codex SDK."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from openai_codex import CodexConfig, CodexError, Sandbox, Thread
from openai_codex.client import CodexClient
from openai_codex.generated.v2_all import ReasoningEffort

from steering import control_turn, identifier, own_thread, steering_endpoint

SOURCE = "antigravity"
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                "output_tokens", "reasoning_output_tokens")


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("new", "resume", "steer", "interrupt", "list"))
    parser.add_argument("--thread", help="Codex thread ID")
    parser.add_argument("--turn", help="Expected active turn ID for steer or interrupt")
    parser.add_argument("--cwd", type=Path, help="Run in this project or the recorded worktree")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--name")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--message", help="Message to send directly")
    inputs.add_argument("--message-file", type=Path, help="Read the exact message from a UTF-8 file")
    parser.add_argument("--mode", choices=("read-only", "workspace-write"))
    parser.add_argument("--model")
    parser.add_argument("--effort", choices=[e.value for e in ReasoningEffort])
    parser.add_argument("--non-git", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--cursor")
    parser.add_argument("--limit", type=int, metavar="1..50",
                        help="Target matches; delegated history includes all matches on the last page")
    args = parser.parse_args()
    if args.model is not None:
        args.model = args.model.strip()
        if not args.model:
            parser.error("--model requires a Codex model ID")
    args.action = args.action or ("resume" if args.thread else "new")
    if args.action in ("list", "interrupt") and (args.message_file is not None or args.message is not None):
        parser.error("--message and --message-file are for new, resume, or steer")
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
    sessions = []
    target = args.limit or (50 if args.all else 20)
    scanned = 0
    cursor = args.cursor
    params = {"sourceKinds": ["exec", "appServer", "cli", "vscode", "unknown"] if args.all
              else ["exec", "vscode", "appServer"], "sortKey": "updated_at",
              "modelProviders": []}
    if args.workspace:
        params["cwd"] = str(args.workspace.resolve(strict=True))
    for _ in range(5):
        # The cursor points past the whole page, so return all its matches.
        page = client.thread_list(dict(params, limit=target if args.all else 20,
                                       cursor=cursor)).model_dump(mode="json", by_alias=True)
        scanned += len(page["data"])
        for row in page["data"]:
            if not args.all:
                source = row.get("threadSource")
                if source is None:
                    source = client.thread_read(row["id"], include_turns=False).thread.thread_source
                if source != SOURCE:
                    continue
            sessions.append({
                "threadId": row["id"], "name": row.get("name") or row["preview"][:72] or row["id"],
                "workingDirectory": row["cwd"],
                "updatedAt": datetime.fromtimestamp(row["updatedAt"], timezone.utc).isoformat(),
            })
        cursor = page.get("nextCursor")
        if args.all or not cursor or len(sessions) >= target:
            break
    return {"sessions": sessions, "nextCursor": cursor, "scanned": scanned}


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
    text = ""
    changed_files = {}
    log = TurnLog()
    usage = dict.fromkeys(TOKEN_FIELDS, 0)
    last_total = None
    for event in turn.stream():
        payload = event.payload
        if event.method == "thread/tokenUsage/updated":
            counts = payload.token_usage
            if counts.total != last_total:
                for field in TOKEN_FIELDS:
                    usage[field] += getattr(counts.last, field) or 0
                last_total = counts.total
        elif event.method == "item/agentMessage/delta":
            log.chunk(payload.item_id, "message", payload.delta)
        elif event.method == "item/commandExecution/outputDelta":
            log.chunk(payload.item_id, "command output", payload.delta)
        elif event.method in ("item/started", "item/completed"):
            item = payload.item.root
            if item.type == "agentMessage" and event.method == "item/completed":
                log.finish(item.id, "message", item.text)
                if item.phase is None or item.phase.value == "final_answer":
                    text = item.text
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
            result = {"status": status, "finalResponse": text, "usage": usage, "changedFiles": list(changed_files)}
            if status == "failed":
                error = payload.turn.error
                result["error"] = error.message if error else "Codex turn failed."
                if error and error.additional_details:
                    result["error"] += f" {error.additional_details}"
            elif status == "completed" and not text.strip():
                result.update(status="failed", error="Codex completed without a final response.")
            return result
    raise RuntimeError("Codex disconnected before completing the turn.")


def mode_file(thread_id):
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return home / "antigravity-codex" / "modes" / identifier(thread_id)


def previous_mode(thread_id):
    try:
        mode = mode_file(thread_id).read_text(encoding="ascii").strip()
    except FileNotFoundError:
        mode = None
    if mode not in ("read-only", "workspace-write"):
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


def run_turn(client, args, prompt, cwd):
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
            effort = args.effort or previous.reasoning_effort
            params["excludeTurns"] = True
        else:
            if not args.non_git:
                git = shutil.which("git")
                if git is None:
                    raise ValueError("Git was not found on PATH. Install Git or use --non-git to skip the Git check.")
                if subprocess.run([git, "rev-parse", "--git-dir"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                    raise ValueError("Use --non-git to start a session outside a Git repository.")
            mode = args.mode or "read-only"
            model, effort = args.model, args.effort
            params["threadSource"] = SOURCE
        if model:
            params["model"] = model
        if effort:
            params["config"] = {"model_reasoning_effort": ReasoningEffort(effort).value}
        params["sandbox"] = mode
        name_warning = None
        try:
            response = client.thread_resume(args.thread, params) if args.thread else client.thread_start(params)
            opened = response.thread.id
            if args.thread and args.thread != opened:
                raise RuntimeError("Codex resumed a different thread.")
            if not args.thread:
                locks.enter_context(own_thread(opened))
            print(f"[codex] Working directory: {cwd}\n[codex] Thread ID: {opened}", file=sys.stderr, flush=True)
            thread = Thread(client, opened)
            if args.name and not args.thread:
                try:
                    thread.set_name(args.name)
                except CodexError as exc:
                    name_warning = f"Could not save session name: {exc}"
                    print(f"[codex] {name_warning}", file=sys.stderr, flush=True)
            model = response.model
            effort = effort or response.reasoning_effort
            turn = thread.turn(prompt, sandbox=Sandbox(mode), effort=ReasoningEffort(effort) if effort else None)
        except CodexError as exc:
            raise RuntimeError(model_error(str(exc), model, effort)) from exc
        with steering_endpoint(turn):
            save_mode(opened, mode)
            print(f"[codex] Turn ID: {turn.id}", file=sys.stderr, flush=True)
            result = collect(turn)
        if result["status"] == "failed":
            result["error"] = model_error(result["error"], model, effort)
        if name_warning:
            result["nameWarning"] = name_warning
        return {"threadId": opened, "turnId": turn.id, "workingDirectory": str(cwd), "mode": mode,
                "model": model, "effort": ReasoningEffort(effort).value if effort else None, **result}


def main():
    args = arguments()
    if args.cwd is not None:
        os.chdir(args.cwd)
    cwd = Path.cwd().resolve(strict=True)
    if args.action != "list":
        if args.workspace and args.workspace.resolve(strict=True) != cwd:
            raise ValueError(f"Run this command in {args.workspace}")
        if args.action == "interrupt":
            return control_turn(args.thread, args.turn, "interrupt")
        if args.message_file is not None:
            prompt = args.message_file.read_bytes().decode("utf-8-sig")
        elif args.message is not None:
            prompt = args.message
        else:
            if sys.stdin.isatty():
                raise ValueError("Pass a message with --message, --message-file, or UTF-8 stdin.")
            prompt = sys.stdin.buffer.read().decode("utf-8-sig")
        if not prompt.strip():
            raise ValueError("The message is empty.")
        if args.action == "steer":
            return control_turn(args.thread, args.turn, "steer", prompt)
    with CodexClient(CodexConfig(cwd=str(cwd))) as client:
        client.initialize()
        if args.action == "list":
            return list_sessions(client, args)
        return run_turn(client, args, prompt, cwd)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        result = main()
        if result.get("status") == "failed":
            print(f"Codex delegation failed: {result['error']}", file=sys.stderr, flush=True)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result.get("status") == "failed":
            sys.exit(1)
        if result.get("status") == "interrupted":
            sys.exit(130)
    except (CodexError, OSError, RuntimeError, ValueError) as error:
        sys.exit(f"Codex delegation failed: {error}")
