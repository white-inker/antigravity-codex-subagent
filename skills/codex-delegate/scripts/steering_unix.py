"""Control active Codex turns through private sockets on Linux and macOS."""
from contextlib import contextmanager
import ctypes
import fcntl
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading

from steering import PACKET_LIMIT, codex_home, control_address_key, dispatch_control, identifier, missing_turn


def runtime_directory():
    # A short path leaves room for the address within the Unix socket path limit.
    directory = Path("/tmp") / f"codex-delegate-{os.geteuid()}"
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise PermissionError(f"Active-turn directory must be private and owned by the current user: {directory}")
    return directory


@contextmanager
def own_thread(thread_id):
    path = runtime_directory() / f"lock-{identifier(codex_home(), thread_id)}"
    # Keep the lock inode in place so competing processes always lock the same file.
    with os.fdopen(os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "rb") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("This thread already has a delegated turn running.") from error
        yield


def socket_address(thread_id, turn_id, mode):
    return runtime_directory() / f"turn-{control_address_key(thread_id, turn_id, mode)}"


def verify_peer(conn):
    if sys.platform == "darwin":
        uid, gid = ctypes.c_uint(), ctypes.c_uint()
        getpeereid = ctypes.CDLL(None, use_errno=True).getpeereid
        getpeereid.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        if getpeereid(conn.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        peer_uid = uid.value
    else:
        credentials = struct.Struct("3i")
        _, peer_uid, _ = credentials.unpack(conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, credentials.size))
    if peer_uid != os.geteuid():
        raise PermissionError("Control socket belongs to a different operating system user.")


def read_packet(conn):
    with conn.makefile("rb") as stream:
        packet = stream.readline(PACKET_LIMIT + 1)
    if not packet:
        raise EOFError("Connection closed.")
    if not packet.endswith(b"\n") or len(packet) > PACKET_LIMIT:
        raise ValueError("Incomplete or oversized control packet.")
    return json.loads(packet)


def write_packet(conn, value):
    packet = json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(packet) > PACKET_LIMIT:
        raise ValueError("Control message exceeds 1 MiB.")
    conn.sendall(packet)


def control_turn(thread_id, turn_id, mode, action, message=None):
    address = socket_address(thread_id, turn_id, mode)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(3)
        try:
            conn.connect(str(address))
        except (FileNotFoundError, ConnectionRefusedError) as error:
            raise missing_turn(thread_id, turn_id) from error
        verify_peer(conn)
        try:
            write_packet(conn, {"action": action, "message": message})
            conn.settimeout(5)
            response = read_packet(conn)
        except (EOFError, OSError) as error:
            raise RuntimeError("Control acknowledgement unavailable. Delivery is unknown.") from error
    if "error" in response:
        raise RuntimeError(response["error"])
    return response


@contextmanager
def steering_endpoint(turn, mode):
    address = socket_address(turn.thread_id, turn.id, mode)
    finished = threading.Event()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        # The runner holds the thread lock while publishing the endpoint.
        address.unlink(missing_ok=True)
        listener.bind(str(address))
        try:
            listener.listen(2)
            listener.settimeout(0.2)

            def serve():
                while not finished.is_set():
                    try:
                        conn, _ = listener.accept()
                    except TimeoutError:
                        continue
                    except OSError as error:
                        print(f"[codex] Active turn control unavailable: {error}", file=sys.stderr, flush=True)
                        return
                    with conn:
                        conn.settimeout(2)
                        try:
                            verify_peer(conn)
                            request = read_packet(conn)
                            if not finished.is_set():
                                write_packet(conn, dispatch_control(turn, request))
                        except (EOFError, OSError, ValueError):
                            continue

            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            try:
                yield
            finally:
                finished.set()
                worker.join(timeout=3)
        finally:
            address.unlink(missing_ok=True)
