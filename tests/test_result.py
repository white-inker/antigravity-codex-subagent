"""Test change reporting and error receipts with SDK file-change events."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-delegate/scripts"))
from codex import collect, model_error, run_turn
from openai_codex.generated.v2_all import ThreadItem


def patch_event(method, status, path, *, destination=None):
    kind = {"type": "update", "move_path": destination} if destination else {"type": "add"}
    item = ThreadItem.model_validate({"type": "fileChange", "id": "patch", "status": status,
                                      "changes": [{"path": path, "kind": kind, "diff": ""}]})
    return SimpleNamespace(method=method, payload=SimpleNamespace(item=item))


class ResultTest(unittest.TestCase):
    def test_changed_files_in_interrupted_turn(self):
        events = [
            patch_event("item/started", "inProgress", "unconfirmed.py"),
            patch_event("item/completed", "completed", "before.py", destination="after.py"),
            patch_event("item/completed", "completed", "after.py"),
            patch_event("item/completed", "failed", "failed.py"),
            SimpleNamespace(method="turn/completed", payload=SimpleNamespace(
                turn=SimpleNamespace(status=SimpleNamespace(value="interrupted")))),
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            result = collect(SimpleNamespace(stream=lambda: iter(events)))
        self.assertEqual(result["changedFiles"], ["before.py", "after.py"])
        self.assertEqual(result["status"], "interrupted")

    def test_model_error_preserves_provider_reason_and_selection(self):
        error = model_error("Reasoning effort is unsupported", "example-model", "high")
        for detail in ("Reasoning effort is unsupported", "model=example-model", "effort=high", "--effort"):
            self.assertIn(detail, error)

    def test_missing_git_has_actionable_error_before_thread_start(self):
        args = SimpleNamespace(thread=None, non_git=False)
        with patch("shutil.which", return_value=None), self.assertRaisesRegex(ValueError, "Install Git or use --non-git"):
            run_turn(None, args, "Inspect", Path.cwd())
