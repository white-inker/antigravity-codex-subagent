"""Antigravity's Windows CLI for the official Codex SDK."""
import argparse
import json
import subprocess
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

from openai_codex import CodexConfig, CodexError, Thread
from openai_codex.client import CodexClient
from openai_codex.generated.v2_all import ReasoningEffort

from steering import own_thread, steer, steering_endpoint

SOURCE = "antigravity"
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                "output_tokens", "reasoning_output_tokens")


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("new", "resume", "steer", "list"))
    parser.add_argument("--thread", help="Codex thread ID")
    parser.add_argument("--turn", help="Expected active turn ID (steer only)")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--message-file", type=Path, help="Read the exact message from a UTF-8 file")
    parser.add_argument("--mode", choices=("read-only", "workspace-write"))
    parser.add_argument("--model")
    parser.add_argument("--effort", choices=[e.value for e in ReasoningEffort])
    parser.add_argument("--non-git", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--cursor")
    args = parser.parse_args()
    if args.model is not None:
        args.model = args.model.strip()
        if not args.model:
            parser.error("--model requires a Codex model ID")
    args.action = args.action or ("resume" if args.thread else "new")
    if args.action == "list" and args.message_file is not None:
        parser.error("--message-file is for new, resume, or steer")
    if args.action in ("resume", "steer") and not args.thread:
        parser.error("resume and steer require --thread")
    if args.action == "new" and args.thread:
        parser.error("new requires a fresh thread")
    if (args.action == "steer") != bool(args.turn):
        parser.error("use --turn with --action steer")
    if args.action == "steer" and any((args.mode, args.model, args.effort, args.non_git, args.name)):
        parser.error("steer only appends a message to the active turn")
    return args


def list_sessions(client, args):
    sessions = []
    params = {"sourceKinds": ["exec", "appServer", "cli", "vscode", "unknown"] if args.all
              else ["exec", "vscode", "appServer"], "sortKey": "updated_at",
              "limit": 50 if args.all else 20, "cursor": args.cursor, "modelProviders": []}
    if args.workspace:
        params["cwd"] = str(args.workspace.resolve(strict=True))
    page = client.thread_list(params).model_dump(mode="json", by_alias=True)
    for row in page["data"]:
        if not args.all:
            source = row.get("threadSource")
            if source is None:
                # SDK 0.172 can omit the source tag in the list response.
                source = client.thread_read(row["id"], include_turns=False).thread.thread_source
            if source != SOURCE:
                continue
        sessions.append({
            "threadId": row["id"], "name": row.get("name") or row["preview"][:72] or row["id"],
            "workingDirectory": row["cwd"],
            "updatedAt": datetime.fromtimestamp(row["updatedAt"], timezone.utc).isoformat(),
        })
    return {"sessions": sessions, "nextCursor": page.get("nextCursor")}


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
        elif event.method == "turn/completed":
            if payload.turn.status.value != "completed":
                error = payload.turn.error
                raise RuntimeError(error.message if error else payload.turn.status.value)
            if not text.strip():
                raise RuntimeError("Codex completed without a final response.")
            return {"finalResponse": text, "usage": usage}
    raise RuntimeError("Codex disconnected before completing the turn.")


def run_turn(client, args, prompt, cwd):
    with ExitStack() as locks:
        params = {"cwd": str(cwd), "approvalPolicy": "never", "sandbox": args.mode or "read-only"}
        if args.thread:
            locks.enter_context(own_thread(args.thread))
            previous = client.thread_read(args.thread).thread
            original = Path(previous.cwd.root).resolve(strict=True)
            if original != cwd:
                raise ValueError(f"Resume in the recorded workspace: {original}")
            model = args.model or previous.model
            effort = args.effort or previous.reasoning_effort
            params["excludeTurns"] = True
        else:
            if not args.non_git and subprocess.run(
                ["git", "rev-parse", "--git-dir"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ).returncode:
                raise ValueError("Use --non-git to start a session outside a Git repository.")
            model, effort = args.model, args.effort
            params["threadSource"] = SOURCE
        if model:
            params["model"] = model
        if effort:
            params["config"] = {"model_reasoning_effort": ReasoningEffort(effort).value}
        if args.thread:
            opened = client.thread_resume(args.thread, params).thread.id
        else:
            opened = client.thread_start(params).thread.id
        if args.thread and args.thread != opened:
            raise RuntimeError("Codex resumed a different thread.")
        if not args.thread:
            locks.enter_context(own_thread(opened))
        thread = Thread(client, opened)
        turn = thread.turn(prompt, effort=ReasoningEffort(effort) if effort else None)
        with steering_endpoint(turn):
            print(f"[codex] Working directory: {cwd}\n[codex] Thread ID: {opened}\n[codex] Turn ID: {turn.id}",
                  file=sys.stderr, flush=True)
            result = collect(turn)
        if args.name and not args.thread:
            try:
                thread.set_name(args.name)
            except CodexError as exc:
                result["nameWarning"] = str(exc)
        return {"threadId": opened, "turnId": turn.id, "workingDirectory": str(cwd), **result}


def main():
    args = arguments()
    cwd = Path.cwd().resolve(strict=True)
    if args.action != "list":
        if args.workspace and args.workspace.resolve(strict=True) != cwd:
            raise ValueError(f"Run this command in {args.workspace}")
        if args.message_file is not None:
            prompt = args.message_file.read_bytes().decode("utf-8-sig")
        else:
            if sys.stdin.isatty():
                raise ValueError("Pass a UTF-8 message on stdin or with --message-file.")
            prompt = sys.stdin.buffer.read().decode("utf-8-sig")
        if not prompt.strip():
            raise ValueError("The message is empty.")
        if args.action == "steer":
            return steer(args.thread, args.turn, prompt)
    with CodexClient(CodexConfig(cwd=str(cwd))) as client:
        client.initialize()
        if args.action == "list":
            return list_sessions(client, args)
        return run_turn(client, args, prompt, cwd)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        print(json.dumps(main(), ensure_ascii=False))
    except (CodexError, OSError, RuntimeError, ValueError) as error:
        sys.exit(f"Codex delegation failed: {error}")
