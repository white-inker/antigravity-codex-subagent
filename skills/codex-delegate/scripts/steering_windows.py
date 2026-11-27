"""Deliver control requests to the owner of an active Codex turn on Windows."""
import ctypes
import _winapi
import json
import threading
import sys
from contextlib import contextmanager
from ctypes import wintypes
from functools import lru_cache
from multiprocessing.connection import PipeConnection
from time import monotonic

from steering import PACKET_LIMIT, codex_home, control_address_key, dispatch_control, identifier, missing_turn

IO_TIMEOUT = 3000
PIPE_REJECT_REMOTE_CLIENTS = 0x8
SECURITY_SQOS_PRESENT = 0x00100000
SECURITY_IDENTIFICATION = 0x00010000
TOKEN_QUERY = 0x0008
TOKEN_USER = 1
SE_KERNEL_OBJECT = 6
OWNER_SECURITY_INFORMATION = 1

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
advapi = ctypes.WinDLL("advapi32", use_last_error=True)
kernel.LocalFree.argtypes = [wintypes.HLOCAL]
kernel.LocalFree.restype = wintypes.HLOCAL
kernel.GetCurrentProcess.restype = wintypes.HANDLE


def sid_text(sid):
    convert = advapi.ConvertSidToStringSidW
    convert.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)]
    result = wintypes.LPWSTR()
    if not convert(sid, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return result.value
    finally:
        kernel.LocalFree(result)


@lru_cache(maxsize=1)
def current_user():
    open_token = advapi.OpenProcessToken
    open_token.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    get_token = advapi.GetTokenInformation
    get_token.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD)]
    token = wintypes.HANDLE()
    if not open_token(kernel.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        get_token(token, TOKEN_USER, None, 0, ctypes.byref(size))
        data = ctypes.create_string_buffer(size.value)
        if not get_token(token, TOKEN_USER, data, size.value, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        # TOKEN_USER starts with SID_AND_ATTRIBUTES, whose first member is the SID pointer.
        return sid_text(ctypes.cast(data, ctypes.POINTER(wintypes.LPVOID))[0])
    finally:
        _winapi.CloseHandle(token.value)


class SecurityAttributes(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("descriptor", wintypes.LPVOID), ("inherit", wintypes.BOOL)]


def new_pipe(address, first=False):
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID), wintypes.LPVOID]
    descriptor = wintypes.LPVOID()
    user = current_user()
    if not convert(f"O:{user}D:P(A;;GA;;;{user})", 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        security = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        flags = _winapi.PIPE_ACCESS_DUPLEX | _winapi.FILE_FLAG_OVERLAPPED
        if first:
            flags |= _winapi.FILE_FLAG_FIRST_PIPE_INSTANCE
        return _winapi.CreateNamedPipe(
            address, flags, _winapi.PIPE_TYPE_MESSAGE | _winapi.PIPE_READMODE_MESSAGE | PIPE_REJECT_REMOTE_CLIENTS,
            2, PACKET_LIMIT, PACKET_LIMIT, IO_TIMEOUT, ctypes.addressof(security))
    finally:
        kernel.LocalFree(descriptor)


def verify_pipe_owner(handle):
    get_security = advapi.GetSecurityInfo
    get_security.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD,
                             ctypes.POINTER(wintypes.LPVOID), wintypes.LPVOID, wintypes.LPVOID,
                             wintypes.LPVOID, ctypes.POINTER(wintypes.LPVOID)]
    get_security.restype = wintypes.DWORD
    owner, descriptor = wintypes.LPVOID(), wintypes.LPVOID()
    error = get_security(handle, SE_KERNEL_OBJECT, OWNER_SECURITY_INFORMATION,
                         ctypes.byref(owner), None, None, None, ctypes.byref(descriptor))
    if error:
        raise ctypes.WinError(error)
    try:
        if sid_text(owner) != current_user():
            raise PermissionError("Control pipe belongs to a different Windows account.")
    finally:
        kernel.LocalFree(descriptor)


@contextmanager
def own_thread(thread_id):
    """The last handle closes automatically on process exit, including a crash."""
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, "Local\\AntigravityCodex-" + identifier(codex_home(), thread_id))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    exists = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    try:
        if exists:
            raise ValueError("This thread already has a delegated turn running.")
        yield
    finally:
        kernel.CloseHandle(handle)


def pipe_address(thread_id, turn_id, mode):
    key = control_address_key(thread_id, turn_id, mode)
    return rf"\\.\pipe\antigravity-codex-control-v3-{key}"


def connect(address):
    deadline = monotonic() + IO_TIMEOUT / 1000
    while True:
        try:
            handle = _winapi.CreateFile(
                address, _winapi.GENERIC_READ | _winapi.GENERIC_WRITE, 0, 0, _winapi.OPEN_EXISTING,
                _winapi.FILE_FLAG_OVERLAPPED | SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION, 0)
            break
        except OSError as error:
            remaining = int((deadline - monotonic()) * 1000)
            if error.winerror != _winapi.ERROR_PIPE_BUSY or remaining <= 0:
                raise
            _winapi.WaitNamedPipe(address, remaining)
    try:
        verify_pipe_owner(handle)
        _winapi.SetNamedPipeHandleState(handle, _winapi.PIPE_READMODE_MESSAGE, None, None)
    except OSError:
        _winapi.CloseHandle(handle)
        raise
    return PipeConnection(handle)


def write_packet(conn, value):
    packet = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if len(packet) > PACKET_LIMIT:
        raise ValueError("Control message exceeds 1 MiB.")
    pending, _ = _winapi.WriteFile(conn.fileno(), packet, overlapped=True)
    if _winapi.WaitForSingleObject(pending.event, IO_TIMEOUT) != _winapi.WAIT_OBJECT_0:
        pending.cancel()
        pending.GetOverlappedResult(True)
        raise TimeoutError("Timed out writing to the control pipe.")
    _, error = pending.GetOverlappedResult(True)
    if error:
        raise ctypes.WinError(error)


def control_turn(thread_id, turn_id, mode, action, message=None):
    address = pipe_address(thread_id, turn_id, mode)
    try:
        connection = connect(address)
    except FileNotFoundError as exc:
        raise missing_turn(thread_id, turn_id) from exc
    with connection:
        try:
            write_packet(connection, {"action": action, "message": message})
            if not connection.poll(5):
                raise TimeoutError("No control acknowledgement.")
            response = json.loads(connection.recv_bytes(PACKET_LIMIT))
        except (EOFError, OSError) as exc:
            raise RuntimeError("Control acknowledgement unavailable. Delivery is unknown.") from exc
    if "error" in response:
        raise RuntimeError(response["error"])
    return response


def wait_for_client(handle, finished):
    pending = _winapi.ConnectNamedPipe(handle, overlapped=True)
    while not finished.is_set():
        if _winapi.WaitForSingleObject(pending.event, 100) == _winapi.WAIT_OBJECT_0:
            _, error = pending.GetOverlappedResult(True)
            if error:
                raise ctypes.WinError(error)
            return True
    pending.cancel()
    pending.GetOverlappedResult(True)
    return False


@contextmanager
def steering_endpoint(turn, mode):
    # The pipe is local to the active turn. The SDK checks its expected turn ID again.
    address = pipe_address(turn.thread_id, turn.id, mode)
    finished = threading.Event()
    first = new_pipe(address, first=True)

    def serve():
        spare = first
        try:
            while not finished.is_set():
                with PipeConnection(spare) as conn:
                    spare = None
                    try:
                        if not wait_for_client(conn.fileno(), finished):
                            return
                    except OSError as error:
                        if error.winerror not in (_winapi.ERROR_NO_DATA, _winapi.ERROR_BROKEN_PIPE):
                            raise
                        spare = new_pipe(address)
                        continue
                    spare = new_pipe(address)
                    try:
                        if not conn.poll(2) or finished.is_set():
                            continue
                        request = json.loads(conn.recv_bytes(PACKET_LIMIT))
                        response = dispatch_control(turn, request)
                    except (EOFError, OSError):
                        continue
                    except (ValueError, TypeError) as exc:
                        response = {"error": str(exc)}
                    try:
                        write_packet(conn, response)
                    except (EOFError, OSError):
                        pass  # Delivery can succeed after the sender leaves.
        except OSError as error:
            print(f"[codex] Active turn control unavailable: {error}", file=sys.stderr, flush=True)
        finally:
            if spare is not None:
                _winapi.CloseHandle(spare)

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield
    finally:
        finished.set()
        worker.join(timeout=3)
