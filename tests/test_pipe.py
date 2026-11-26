"""Exercise local pipe ownership, disconnects and bounded teardown."""
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-delegate/scripts"))
from steering import connect, control_turn, own_thread, pipe_address, steering_endpoint


class PipeTest(unittest.TestCase):
    def test_wrong_owner_rejected_and_disconnect_does_not_stop_listener(self):
        turn = SimpleNamespace(thread_id=uuid4().hex, id=uuid4().hex, interrupt=lambda: None)
        with steering_endpoint(turn, "read-only"):
            address = pipe_address(turn.thread_id, turn.id, "read-only")
            with patch("steering.current_user", return_value="S-1-5-18"):
                with self.assertRaisesRegex(PermissionError, "different Windows account"):
                    connect(address)
            with connect(address):
                pass
            response = control_turn(turn.thread_id, turn.id, "read-only", "interrupt")
        self.assertEqual(response["status"], "interruptRequested")

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
