"""Exercise the installed command as PowerShell parses it on Windows."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import manage


@unittest.skipUnless(sys.platform == "win32", "Windows PowerShell launcher")
class InstallTest(unittest.TestCase):
    def test_launcher_in_profile_with_spaces_and_apostrophe(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "O'Brien profile" / ".gemini" / "config"
            skill = manage.SKILL / "SKILL.md"
            manage.deploy(skill, config)
            installed = (config / skill).read_text(encoding="utf-8")
            scripts = config / manage.SCRIPTS
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", scripts / ".venv"], check=True)
            (scripts / "codex.py").write_text(
                "import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")

            sample = next(line for line in installed.splitlines() if " --action new --name " in line)
            prefix = sample.split(" --cwd ", 1)[0]
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", prefix + " --message=-v"],
                cwd=temp, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), ["--message=-v"])
            manager = str(manage.ROOT / "manage.py").replace("'", "''")
            self.assertIn(f"python '{manager}' install", installed)
