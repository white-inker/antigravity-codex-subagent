"""Regression tests for bounded history queries through the Codex SDK."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-delegate/scripts"))
from codex import list_sessions


class HistoryTest(unittest.TestCase):
    def test_empty_filtered_page_can_be_continued(self):
        client = Mock()
        page = client.thread_list.return_value.model_dump
        page.side_effect = [
            {"data": [{"id": str(i)} for i in range(20)], "nextCursor": "next"},
            {"data": [{"id": "a", "threadSource": "antigravity", "name": "example",
                       "cwd": "project", "updatedAt": 0}, {"id": "b", "threadSource": "user"}],
             "nextCursor": None},
        ]
        client.thread_read.return_value.thread.thread_source = "user"
        args = SimpleNamespace(all=False, cursor=None, workspace=None)
        result = list_sessions(client, args)
        self.assertEqual(result, {"sessions": [], "nextCursor": "next"})
        self.assertEqual(client.thread_list.call_count, 1)
        self.assertEqual(client.thread_list.call_args.args[0]["limit"], 20)
        self.assertEqual(client.thread_read.call_count, 20)

        args.cursor = result["nextCursor"]
        result = list_sessions(client, args)
        self.assertEqual([s["threadId"] for s in result["sessions"]], ["a"])
        self.assertIsNone(result["nextCursor"])
        self.assertEqual(client.thread_list.call_args.args[0]["cursor"], "next")
        self.assertEqual(client.thread_read.call_count, 20)

    def test_all_uses_only_the_list_response(self):
        client = Mock()
        client.thread_list.return_value.model_dump.return_value = {
            "data": [{"id": "other", "name": "ordinary", "cwd": "project", "updatedAt": 0}],
            "nextCursor": "next",
        }
        result = list_sessions(client, SimpleNamespace(all=True, cursor=None, workspace=None))
        self.assertEqual(result["sessions"][0]["threadId"], "other")
        self.assertEqual(result["nextCursor"], "next")
        client.thread_read.assert_not_called()
