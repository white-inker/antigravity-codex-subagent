"""Exercise local pipe ownership, disconnects and bounded teardown."""
from contextlib import ExitStack
import json
import os
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-delegate/scripts"))
if sys.platform == "win32":
    from steering_windows import connect, control_turn, own_thread, pipe_address, steering_endpoint
else:
    from steering_unix import (
        PACKET_LIMIT, control_address_key, control_turn, own_thread, runtime_directory, socket_address,
        steering_endpoint, verify_peer,
    )


class PipeTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Win32 pipe ownership")
    def test_wrong_owner_rejected_and_disconnect_does_not_stop_listener(self):
        turn = SimpleNamespace(thread_id=uuid4().hex, id=uuid4().hex, interrupt=lambda: None)
        with steering_endpoint(turn, "read-only"):
            address = pipe_address(turn.thread_id, turn.id, "read-only")
            with patch("steering_windows.current_user", return_value="S-1-5-18"):
                with self.assertRaisesRegex(PermissionError, "different Windows account"):
                    connect(address)
            with connect(address):
                pass
            response = control_turn(turn.thread_id, turn.id, "read-only", "interrupt")
        self.assertEqual(response["status"], "interruptRequested")

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "Unix control socket")
    def test_unix_socket_is_private_and_removed_when_turn_finishes(self):
        turn = SimpleNamespace(thread_id=uuid4().hex, id=uuid4().hex, interrupt=lambda: None)
        with steering_endpoint(turn, "workspace-write"):
            path = socket_address(turn.thread_id, turn.id, "workspace-write")
            self.assertEqual(runtime_directory().stat().st_mode & 0o777, 0o700)
            self.assertTrue(path.is_socket())
            with self.assertRaisesRegex(ValueError, "No active turn"):
                control_turn(turn.thread_id, turn.id, "read-only", "interrupt")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.connect(str(path))
            self.assertEqual(control_turn(turn.thread_id, turn.id, "workspace-write", "interrupt")["status"],
                             "interruptRequested")
        self.assertFalse(path.exists())

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "Unix control socket")
    def test_unix_rejects_invalid_packets_without_stopping_listener(self):
        turn = SimpleNamespace(thread_id=uuid4().hex, id=uuid4().hex, interrupt=lambda: None)
        with steering_endpoint(turn, "read-only"):
            path = socket_address(turn.thread_id, turn.id, "read-only")
            for packet in (b"{invalid}\n", b"x" * PACKET_LIMIT + b"\n"):
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                    conn.settimeout(3)
                    conn.connect(str(path))
                    conn.sendall(packet)
                    with conn.makefile("rb") as stream:
                        self.assertIn("error", json.loads(stream.readline()))
            self.assertEqual(control_turn(turn.thread_id, turn.id, "read-only", "interrupt")["status"],
                             "interruptRequested")

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "Unix control socket")
    def test_unix_socket_name_fits_macos_with_a_large_uid(self):
        with patch("steering_unix.runtime_directory", return_value=Path("/tmp/codex-delegate-4294967294")):
            path = socket_address("thread", "turn", "read-only")
        self.assertLessEqual(len(os.fsencode(path)), 103)
        self.assertEqual(len(path.name.removeprefix("turn-")), 32)

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "Unix control socket")
    def test_client_can_control_turn_started_before_socket_names_were_shortened(self):
        turn = SimpleNamespace(thread_id=uuid4().hex, id=uuid4().hex, interrupt=lambda: None)
        legacy = runtime_directory() / f"turn-{control_address_key(turn.thread_id, turn.id, 'read-only')}"
        with ExitStack() as stack:
            with patch("steering_unix.socket_address", return_value=legacy):
                stack.enter_context(steering_endpoint(turn, "read-only"))
            self.assertEqual(control_turn(turn.thread_id, turn.id, "read-only", "interrupt")["status"],
                             "interruptRequested")

    @unittest.skipUnless(sys.platform == "linux", "Linux peer credentials")
    def test_linux_peer_uid_is_unsigned(self):
        uid = 2**31 + 123
        conn = Mock()
        conn.getsockopt.return_value = struct.pack("iII", 1234, uid, uid)
        with patch("steering_unix.os.geteuid", return_value=uid):
            verify_peer(conn)

    def test_owner_exits_even_if_sdk_control_has_not_returned(self):
        entered = threading.Event()
        released = threading.Event()

        def stall():
            entered.set()
            released.wait(15)

        turn = SimpleNamespace(thread_id=uuid4().hex, id=uuid4().hex, interrupt=stall)
        try:
            with steering_endpoint(turn, "read-only"):
                def control():
                    try:
                        control_turn(turn.thread_id, turn.id, "read-only", "interrupt")
                    except RuntimeError:
                        pass  # The client can miss the acknowledgement once teardown starts.
                caller = threading.Thread(target=control, daemon=True)
                caller.start()
                self.assertTrue(entered.wait(3))
            self.assertFalse(released.is_set())
            self.assertTrue(caller.is_alive(), "endpoint waited for the stuck control")
        finally:
            released.set()
        caller.join(timeout=3)

    def test_thread_lock_uses_codex_home(self):
        thread_id = uuid4().hex
        with patch.dict("os.environ", CODEX_HOME="test-home-a"), own_thread(thread_id):
            with patch.dict("os.environ", CODEX_HOME="test-home-b"), own_thread(thread_id):
                with self.assertRaisesRegex(ValueError, "already has"):
                    with own_thread(thread_id):
                        pass
