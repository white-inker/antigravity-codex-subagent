"""Check that a relocated skill emits usable, distinct launcher prefixes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import manage
sys.path.insert(0, str(manage.ROOT / manage.SCRIPTS))
import setup_runtime


class InstallTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell launcher")
    def test_safe_executable_path_starts_the_approval_prefix(self):
        exe = Path(r"C:\Users\sample\.venv\Scripts\python.exe")
        runner = Path(r"C:\Users\sample\codex_ro.py")
        self.assertEqual(setup_runtime.launcher_prefix(exe, runner), f"{exe} '{runner}'")

    def test_launcher_in_profile_with_spaces_and_apostrophe(self):
        with tempfile.TemporaryDirectory() as temp:
            scripts = Path(temp) / "O'Brien profile" / "custom skills" / "codex-delegate" / "scripts"
            scripts.mkdir(parents=True)
            with patch.object(Path, "home", return_value=Path(temp) / "O'Brien profile"):
                subprocess.run([sys.executable, "-m", "venv", "--without-pip", setup_runtime.runtime_env()],
                               check=True)
                with patch.object(setup_runtime, "SCRIPTS", scripts):
                    paths = setup_runtime.launchers()
            self.assertTrue(paths["runtimeExists"])
            shell = (["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]
                     if sys.platform == "win32" else ["/bin/sh", "-c"])
            for key, launcher in (("readOnly", "codex_ro.py"), ("workspaceWrite", "codex_rw.py")):
                (scripts / launcher).write_text(
                    "import json, sys\nprint(json.dumps(sys.argv))\n", encoding="utf-8")
                result = subprocess.run(
                    [*shell, paths[key] + " --message=-v"],
                    cwd=temp, capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(result.stdout), [str(scripts / launcher), "--message=-v"])
