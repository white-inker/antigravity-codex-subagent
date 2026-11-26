"""Regression tests for bounded history queries through the Codex SDK."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/codex-delegate/scripts"))
from codex import list_sessions


class HistoryTest(unittest.TestCase):
    def test_limit_one_finds_matches_beyond_five_unrelated_threads(self):
        client = Mock()
        rows = [{"id": str(i), "threadSource": "antigravity" if i in (27, 32, 46) else "user",
                 "name": str(i), "cwd": "project", "updatedAt": 100 - i} for i in range(60)]

        def fetch(params):
            offset = int(params["cursor"] or 0)
            end = offset + params["limit"]
            return Mock(model_dump=lambda **kwargs: {
                "data": rows[offset:end], "nextCursor": str(end) if end < len(rows) else None})

        client.thread_list.side_effect = fetch
        args = SimpleNamespace(all=False, cursor=None, workspace=None, limit=1)
        result = list_sessions(client, args)
        self.assertEqual([row["threadId"] for row in result["sessions"]], ["27", "32"])
        self.assertEqual(result["scanned"], 40)
        args.cursor = result["nextCursor"]
        more = list_sessions(client, args)
        self.assertEqual([row["threadId"] for row in more["sessions"]], ["46"])
        self.assertIsNone(more["nextCursor"])

    def test_empty_filtered_page_is_scanned_in_the_same_call(self):
        client = Mock()
        page = client.thread_list.return_value.model_dump
        page.side_effect = [
            {"data": [{"id": str(i)} for i in range(20)], "nextCursor": "next"},
            {"data": [{"id": "a", "threadSource": "antigravity", "name": "example",
                       "cwd": "project", "updatedAt": 0}, {"id": "b", "threadSource": "user"}],
             "nextCursor": None},
        ]
        client.thread_read.return_value.thread.thread_source = "user"
        args = SimpleNamespace(all=False, cursor=None, workspace=None, limit=None)
        result = list_sessions(client, args)
        self.assertEqual(client.thread_list.call_count, 2)
        self.assertEqual(result["scanned"], 22)
        self.assertEqual([s["threadId"] for s in result["sessions"]], ["a"])
        self.assertIsNone(result["nextCursor"])
        self.assertEqual(client.thread_list.call_args.args[0]["cursor"], "next")
        self.assertEqual(client.thread_read.call_count, 20)

    def test_scan_cap_preserves_cursor(self):
        client = Mock()
        client.thread_list.return_value.model_dump.side_effect = [
            {"data": [{"id": f"{i}-{j}", "threadSource": "user"} for j in range(20)], "nextCursor": str(i)}
            for i in range(1, 6)
        ]
        result = list_sessions(client, SimpleNamespace(all=False, cursor=None, workspace=None, limit=None))
        self.assertEqual(result, {"sessions": [], "nextCursor": "5", "scanned": 100})
        self.assertEqual(client.thread_list.call_count, 5)

    def test_filtered_pages_keep_their_scan_size(self):
        client = Mock()
        row = {"threadSource": "antigravity", "name": "test", "cwd": "test", "updatedAt": 0}
        client.thread_list.return_value.model_dump.side_effect = [
            {"data": [dict(row, id="a"), {"id": "unrelated", "threadSource": "user"}], "nextCursor": "page2"},
            {"data": [dict(row, id="b")], "nextCursor": "page3"},
        ]
        result = list_sessions(client, SimpleNamespace(all=False, cursor=None, workspace=None, limit=2))
        self.assertEqual([s["threadId"] for s in result["sessions"]], ["a", "b"])
        self.assertEqual(client.thread_list.call_args.args[0]["limit"], 20)
        self.assertEqual(result["nextCursor"], "page3")

    def test_all_uses_only_the_list_response(self):
        client = Mock()
        client.thread_list.return_value.model_dump.return_value = {
            "data": [{"id": "other", "name": "ordinary", "cwd": "project", "updatedAt": 0}],
            "nextCursor": "next",
        }
        result = list_sessions(client, SimpleNamespace(all=True, cursor=None, workspace=None, limit=1))
        self.assertEqual(client.thread_list.call_args.args[0]["limit"], 1)
        self.assertEqual(result["sessions"][0]["threadId"], "other")
        self.assertEqual(result["nextCursor"], "next")
        client.thread_read.assert_not_called()
