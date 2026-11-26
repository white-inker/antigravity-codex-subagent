"""Deliver control requests to the owner of an active Codex turn on Windows."""
import ctypes
import hashlib
import json
import os
import threading
from contextlib import contextmanager
from ctypes import wintypes
from multiprocessing.connection import Client, Listener
from pathlib import Path

from openai_codex import CodexError


def identifier(*parts):
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


@contextmanager
def own_thread(thread_id):
    """The last handle closes automatically on process exit, including a crash."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, "Local\\AntigravityCodex-" + identifier(thread_id))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    exists = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    try:
        if exists:
            raise ValueError("This thread already has a delegated turn running.")
        yield
    finally:
        kernel.CloseHandle(handle)


def pipe_address(thread_id, turn_id):
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).resolve()
    workspace = Path.cwd().resolve(strict=True)
    key = identifier(os.path.normcase(str(home)), os.path.normcase(str(workspace)), thread_id, turn_id)
    # Older owners accepted unframed prompt text. Never send a control packet there.
    return rf"\\.\pipe\antigravity-codex-control-v2-{key}"


def control_turn(thread_id, turn_id, action, message=None):
    address = pipe_address(thread_id, turn_id)
    try:
        connection = Client(address, family="AF_PIPE")
    except FileNotFoundError as exc:
        raise ValueError(f"No active turn matches {Path.cwd().resolve()}, thread {thread_id}, turn {turn_id}. "
                         "Use the original task's Working directory and IDs, and the same CODEX_HOME.") from exc
    with connection:
        try:
            connection.send_bytes(json.dumps({"action": action, "message": message}).encode())
            response = json.loads(connection.recv_bytes())
        except (EOFError, BrokenPipeError) as exc:
            raise RuntimeError("Connection closed before acknowledgement. Delivery is unknown.") from exc
    if "error" in response:
        raise RuntimeError(response["error"])
    return response


@contextmanager
def steering_endpoint(turn):
    # The pipe is local to the active turn. The SDK checks its expected turn ID again.
    address = pipe_address(turn.thread_id, turn.id)
    finished = threading.Event()
    with Listener(address, family="AF_PIPE") as listener:
        def serve():
            while True:
                with listener.accept() as conn:
                    if finished.is_set():
                        return
                    try:
                        if not conn.poll(5):
                            continue
                        request = json.loads(conn.recv_bytes())
                        if request["action"] == "interrupt":
                            turn.interrupt()
                            status = "interruptRequested"
                            accepted_turn = turn.id
                        elif request["action"] == "steer":
                            accepted_turn = turn.steer(request["message"]).turn_id
                            status = "accepted"
                        else:
                            raise ValueError("Unknown active-turn action")
                        response = {"status": status, "threadId": turn.thread_id, "turnId": accepted_turn}
                    except (EOFError, BrokenPipeError):
                        continue
                    except (CodexError, RuntimeError, ValueError, KeyError, TypeError) as exc:
                        response = {"error": str(exc)}
                    try:
                        conn.send_bytes(json.dumps(response).encode())
                    except (EOFError, BrokenPipeError):
                        pass  # The sender disconnected after delivery.
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            yield
        finally:
            finished.set()
            # Wake a blocked accept and finish any SDK acknowledgement before teardown.
            with Client(address, family="AF_PIPE"):
                pass
            worker.join()
