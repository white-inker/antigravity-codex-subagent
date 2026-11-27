"""Shared addressing and message dispatch for active Codex turns."""
import hashlib
import os
from pathlib import Path

from openai_codex import CodexError

PACKET_LIMIT = 1024 * 1024


def identifier(*parts):
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


def codex_home():
    return os.path.normcase(str(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).resolve()))


def control_address_key(thread_id, turn_id, mode):
    workspace = os.path.normcase(str(Path.cwd().resolve(strict=True)))
    return identifier(codex_home(), workspace, thread_id, turn_id, mode)


def missing_turn(thread_id, turn_id):
    return ValueError(f"No active turn matches {Path.cwd().resolve()}, thread {thread_id}, turn {turn_id}. "
                      "Use the original task's Working directory, IDs, launcher and CODEX_HOME.")


def dispatch_control(turn, request):
    try:
        if request["action"] == "interrupt":
            turn.interrupt()
            status, accepted_turn = "interruptRequested", turn.id
        elif request["action"] == "steer":
            status, accepted_turn = "accepted", turn.steer(request["message"]).turn_id
        else:
            raise ValueError("Unknown active-turn action")
        return {"status": status, "threadId": turn.thread_id, "turnId": accepted_turn}
    except (CodexError, RuntimeError, ValueError, KeyError, TypeError) as error:
        return {"error": str(error)}
