"""Integration regression for live steering. Uses a loopback provider and a fresh CODEX_HOME."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RUNNER = Path(__file__).resolve().parents[1] / "skills/codex-delegate/scripts/codex.py"
ANSWER = "检查完成"
PROGRESS = "正在检查超时路径"


class ModelEndpoint(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(request)
        i = len(self.server.requests)
        item = {"id": f"msg_{i}", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": ANSWER, "annotations": []}]}
        response = {"id": f"resp_{i}", "object": "response", "model": request["model"],
                    "status": "completed", "output": [item],
                    "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}
        events = [("response.created", {"response": {"id": response["id"], "status": "in_progress"}})]
        if i == 1:
            update = dict(item, id="progress", phase="commentary",
                          content=[{"type": "output_text", "text": PROGRESS + "\n"}])
            events.extend([
                ("response.output_item.added", {"output_index": 0, "item": dict(update, content=[], status="in_progress")}),
                ("response.output_text.delta", {"item_id": "progress", "output_index": 0,
                                                "content_index": 0, "delta": PROGRESS + "\n"}),
                ("response.output_item.done", {"output_index": 0, "item": update}),
            ])
            response["output"].insert(0, update)
        index = len(response["output"]) - 1
        events.extend([
            ("response.output_item.added", {"output_index": index, "item": dict(item, content=[])}),
            ("response.output_item.done", {"output_index": index, "item": item}),
            ("response.completed", {"response": response}),
        ])
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for kind, body in events:
            try:
                self.wfile.write(("data: " + json.dumps(dict(body, type=kind)) + "\n\n").encode())
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                if i == 1 and self.server.release.is_set():
                    return  # Steering can close the provider stream for the superseded request.
                raise
            if kind == "response.output_text.delta":
                self.wfile.flush()
                self.server.started.set()
                self.server.delivery_timed_out = not self.server.release.wait(25)


@unittest.skipUnless(sys.platform == "win32", "Windows named pipe transport")
class SteeringTest(unittest.TestCase):
    def test_steer_while_provider_is_busy(self):
        contexts = ExitStack()
        self.addCleanup(contexts.close)
        root = Path(contexts.enter_context(tempfile.TemporaryDirectory()))
        home, project = root / "home", root / "project"
        home.mkdir()
        project.mkdir()
        server = contexts.enter_context(ThreadingHTTPServer(("127.0.0.1", 0), ModelEndpoint))
        server.started, server.release = threading.Event(), threading.Event()
        server.delivery_timed_out = False
        server.requests = []
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        (home / "config.toml").write_text(
            'model = "gpt-5.4"\nmodel_provider = "test"\n[model_providers.test]\n'
            f'name = "test"\nbase_url = "http://127.0.0.1:{server.server_port}/v1"\n'
            'wire_api = "responses"\nsupports_websockets = false\n', encoding="utf8")
        env = dict(os.environ, CODEX_HOME=str(home), HTTP_PROXY="http://127.0.0.1:1",
                   HTTPS_PROXY="http://127.0.0.1:1", NO_PROXY="127.0.0.1,localhost")
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
            env.pop(key, None)

        def call(*args, message="", cwd=project, error=None):
            p = subprocess.run([sys.executable, str(RUNNER), *args], input=message,
                               cwd=cwd, env=env, capture_output=True, encoding="utf-8", timeout=30)
            if error is not None:
                self.assertNotEqual(p.returncode, 0)
                self.assertIn(error, p.stderr)
                return
            self.assertEqual(p.returncode, 0, p.stderr)
            return json.loads(p.stdout)

        cmd = [sys.executable, str(RUNNER), "--action", "new", "--non-git", "--name", "first",
               "--model", "gpt-6.2-astra", "--effort", "high"]
        with subprocess.Popen(cmd, cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, encoding="utf8") as owner:
            owner.stdin.write("Investigate the original problem.")
            owner.stdin.close()
            owner.stdin = None
            try:
                self.assertTrue(server.started.wait(15))
                ids = {}
                for line in owner.stderr:
                    for key in ("Thread ID", "Turn ID"):
                        if line.startswith(f"[codex] {key}: "):
                            ids[key] = line.split(": ", 1)[1].strip()
                    if PROGRESS in line:
                        break
                self.assertIn(PROGRESS, line)
                self.assertFalse(server.delivery_timed_out, "Progress arrived only after the item completed")
                thread_id, turn_id = ids["Thread ID"], ids["Turn ID"]
                route = ["--action", "steer", "--thread", thread_id, "--turn"]
                call(*route, "stale", message="wrong turn", error="No active turn")
                subdirectory = project / "subdirectory"
                subdirectory.mkdir()
                call(*route, turn_id, cwd=subdirectory, message="wrong workspace", error="No active turn")
                call("--action", "resume", "--thread", thread_id, message="overlap", error="already has a delegated")
                message = "请检查这段原文：\r\n'@\r\nKeep $name unchanged."
                message_file = root / "literal message.txt"
                message_file.write_bytes(message.encode("utf-8"))
                receipt = call(*route, turn_id, "--message-file", str(message_file), cwd=subdirectory / "..")
                self.assertEqual(receipt, {"status": "accepted", "threadId": thread_id, "turnId": turn_id})
                self.assertIsNone(owner.poll())
            finally:
                server.release.set()
            output, errors = owner.communicate(timeout=30)
            self.assertEqual(owner.returncode, 0, errors)
        self.assertIn(ANSWER, output)
        result = json.loads(output)
        self.assertEqual((result["threadId"], result["turnId"], result["finalResponse"]), (thread_id, turn_id, ANSWER))
        user_text = [part.get("text") for req in server.requests[1:] for item in req["input"]
                     if item.get("role") == "user" for part in item.get("content", [])]
        self.assertIn(message, user_text)
        call("--action", "new", "--effort", "persistent", message="test", error="invalid choice")
        call(*route, turn_id, message="too late", error="No active turn")
        self.assertIn(thread_id, [s["threadId"] for s in call("--action", "list")["sessions"]])
        next_turn = call("--action", "resume", "--thread", thread_id, message="Follow-up")
        self.assertEqual(next_turn["threadId"], thread_id)
        self.assertNotEqual(next_turn["turnId"], turn_id)
        self.assertEqual(next_turn["usage"]["input_tokens"], 10)
        self.assertEqual(server.requests[-1]["reasoning"]["effort"], "high")


if __name__ == "__main__":
    unittest.main()
