"""Test change reporting and error receipts with SDK file-change events."""
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-delegate/scripts"))
from codex import TOKEN_FIELDS, collect, model_error, remove_delivered_message, run_turn, scratch_message_path
from workspace import workspace_changes, workspace_snapshot
from openai_codex.generated.v2_all import ThreadItem


def patch_event(method, status, path, *, destination=None):
    kind = {"type": "update", "move_path": destination} if destination else {"type": "add"}
    item = ThreadItem.model_validate({"type": "fileChange", "id": "patch", "status": status,
                                      "changes": [{"path": path, "kind": kind, "diff": ""}]})
    return SimpleNamespace(method=method, payload=SimpleNamespace(item=item))


class ResultTest(unittest.TestCase):
    def test_combine_final_items_and_allow_completion_without_text(self):
        def answer(id, text, phase):
            item = ThreadItem.model_validate({"type": "agentMessage", "id": id, "text": text, "phase": phase})
            return SimpleNamespace(method="item/completed", payload=SimpleNamespace(item=item))

        completed = SimpleNamespace(method="turn/completed", payload=SimpleNamespace(
            turn=SimpleNamespace(status=SimpleNamespace(value="completed"))))
        events = [answer("1", "First", "final_answer"), answer("2", "Progress", "commentary"),
                  answer("3", "Last", None), completed]
        with contextlib.redirect_stderr(io.StringIO()):
            result = collect(SimpleNamespace(stream=lambda: iter(events)))
            empty = collect(SimpleNamespace(stream=lambda: iter([completed])))
        self.assertEqual(result["finalResponse"], "First\n\nLast")
        self.assertEqual((empty["status"], empty["finalResponse"]), ("completed", ""))

    def test_scratch_messages_use_allowed_directories_outside_the_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            profile = root / "profile"
            system_temp = root / "system-temp"
            skill_scratch = profile / ".codex-delegate/scratch"
            host_scratch = profile / ".gemini/antigravity/brain/conversation/scratch"
            project = system_temp / "project"
            filename = f"codex-message-{'f' * 32}.txt"
            allowed = (system_temp, system_temp / "agent", skill_scratch,
                       skill_scratch / "conversation", host_scratch)
            too_deep = (system_temp / "agent/subfolder", skill_scratch / "agent/subfolder")
            for directory in (*allowed, *too_deep, project, project / "subdir"):
                directory.mkdir(parents=True, exist_ok=True)
                (directory / filename).write_bytes(b"message")
            existing = host_scratch / "instructions.txt"
            existing.write_bytes(b"keep")
            nonfile = system_temp / f"codex-message-{'a' * 32}.txt"
            nonfile.mkdir()
            with patch.object(Path, "home", return_value=profile), patch("codex.gettempdir", return_value=str(system_temp)):
                for directory in allowed:
                    message = directory / filename
                    self.assertEqual(scratch_message_path(message, project), message)
                for directory in too_deep:
                    with self.assertRaisesRegex(ValueError, "allowed temporary directory"):
                        scratch_message_path(directory / filename, project)
                for directory in (project, project / "subdir"):
                    with self.assertRaisesRegex(ValueError, "inside the project"):
                        scratch_message_path(directory / filename, project)
                with self.assertRaisesRegex(ValueError, "generated scratch message"):
                    scratch_message_path(existing, project)
                with self.assertRaisesRegex(ValueError, "regular file"):
                    scratch_message_path(nonfile, project)
                remove_delivered_message(system_temp / "agent" / filename, project)
            self.assertTrue((system_temp / "agent").is_dir())
            self.assertFalse((system_temp / "agent" / filename).exists())

    @unittest.skipIf(sys.platform == "win32", "Creating symlinks may require Windows Developer Mode")
    def test_cleanup_rechecks_symlinks_and_project_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            system_temp = Path(temp).resolve()
            project = system_temp / "project"
            project.mkdir()
            scratch = system_temp / "agent"
            scratch.mkdir()
            name = f"codex-message-{'f' * 32}.txt"
            protected = project / name
            protected.write_bytes(b"keep")
            message = scratch / name
            with patch("codex.gettempdir", return_value=str(system_temp)):
                message.symlink_to(protected)
                with self.assertRaisesRegex(ValueError, "regular file"):
                    scratch_message_path(message, project)
                message.unlink()
                message.write_bytes(b"deliver")
                accepted = scratch_message_path(message, project)
                scratch.rename(system_temp / "prev")
                scratch.symlink_to(project, target_is_directory=True)
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    remove_delivered_message(accepted, project)
                self.assertIn("inside the project", errors.getvalue())
            self.assertEqual(protected.read_bytes(), b"keep")

    def test_usage_is_difference_between_cumulative_snapshots(self):
        def usage(total, last):
            counts = SimpleNamespace(
                total=SimpleNamespace(**dict.fromkeys(TOKEN_FIELDS, total)),
                last=SimpleNamespace(**dict.fromkeys(TOKEN_FIELDS, last)))
            return SimpleNamespace(method="thread/tokenUsage/updated", payload=SimpleNamespace(token_usage=counts))

        complete = SimpleNamespace(method="turn/completed", payload=SimpleNamespace(
            turn=SimpleNamespace(status=SimpleNamespace(value="completed"))))
        first = usage(110, 10)
        events = [first, first, usage(145, 5), complete]
        result = collect(SimpleNamespace(stream=lambda: iter(events)))
        self.assertEqual(result["usage"], dict.fromkeys(TOKEN_FIELDS, 45))

    def test_workspace_changes_include_shell_writes_and_exclude_preexisting_files(self):
        with tempfile.TemporaryDirectory() as temp:
            cwd = Path(temp)
            subprocess.run(["git", "init", "-q", cwd], check=True, capture_output=True)
            (cwd / "existing.txt").write_text("already here", encoding="utf-8")
            (cwd / "modified.txt").write_text("old", encoding="utf-8")
            subprocess.run(["git", "add", "modified.txt"], cwd=cwd, check=True, capture_output=True)
            before = workspace_snapshot(cwd)
            (cwd / "modified.txt").write_text("new content", encoding="utf-8")
            (cwd / "created.txt").write_text("written by tool", encoding="utf-8")
            alias = str(Path("nested") / ".." / "modified.txt")
            changes = workspace_changes(cwd, before, [alias, "modified.txt"])
            self.assertEqual(changes, {"changeTracking": "sdk-patches-and-git-worktree",
                                       "changedFiles": [alias, "created.txt"]})
            with patch("workspace.MAX_SNAPSHOT_FILES", 1):
                self.assertEqual(workspace_changes(cwd, before, []),
                                 {"changeTracking": "sdk-patches", "changeTrackingReason": "snapshot-file-limit"})

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
        with patch("codex.git_executable", return_value=None), self.assertRaisesRegex(ValueError, "Install Git or use --non-git"):
            run_turn(None, args, "Inspect", Path.cwd())
