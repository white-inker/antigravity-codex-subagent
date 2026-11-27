"""Check that a relocated skill emits usable, distinct launcher prefixes."""
import json
import os
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
        self.assertEqual(setup_runtime.launcher_prefix(exe, runner, "powershell"), f"{exe} '{runner}'")

    def test_launcher_in_profile_with_spaces_and_apostrophe(self):
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / "O'Brien 中文 profile"
            scripts = profile / "custom skills" / "codex-delegate" / "scripts"
            scripts.mkdir(parents=True)
            with patch.object(Path, "home", return_value=profile):
                env, _ = setup_runtime.runtime_location()
                subprocess.run([sys.executable, "-m", "venv", "--without-pip", env], check=True)
                with patch.object(setup_runtime, "SCRIPTS", scripts):
                    paths = setup_runtime.launchers()
            self.assertTrue(paths["runtimeExists"])
            if sys.platform == "win32":
                git_bash = Path(os.environ["ProgramFiles"]) / "Git/bin/bash.exe"
                shells = {
                    "powershell": lambda command: ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                    "bash": lambda command: [str(git_bash), "--noprofile", "--norc", "-c", command],
                    "cmd": lambda command: f'cmd.exe /d /v:off /s /c "{command}"',
                }
            else:
                shells = {"bash": lambda command: ["/bin/bash", "-c", command]}
            for key, launcher in (("readOnly", "codex_ro.py"), ("workspaceWrite", "codex_rw.py")):
                (scripts / launcher).write_text(
                    "import json, sys\nprint(json.dumps(sys.argv))\n", encoding="utf-8")
                for shell, command in shells.items():
                    if shell == "bash" and sys.platform == "win32" and not git_bash.is_file():
                        continue
                    with self.subTest(shell=shell, launcher=launcher):
                        result = subprocess.run(command(paths["shells"][shell][key] + " --message=-v"),
                                                cwd=temp, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        script, option = json.loads(result.stdout)
                        self.assertEqual(Path(script).resolve(), (scripts / launcher).resolve())
                        self.assertEqual(option, "--message=-v")

    def test_paths_distinguishes_denied_runtime_from_missing_runtime(self):
        with patch.object(Path, "stat", side_effect=[FileNotFoundError(), PermissionError()]):
            paths = setup_runtime.launchers("bash")
        self.assertIsNone(paths["runtimeExists"])
        self.assertEqual(paths["runtimeStatus"], "inaccessible")
        self.assertEqual(paths["shell"], "bash")
        self.assertEqual(paths["readOnly"], paths["shells"]["bash"]["readOnly"])

    def test_paths_prints_utf8_json(self):
        profile_var = "USERPROFILE" if sys.platform == "win32" else "HOME"
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / "中文"
            profile.mkdir()
            output = subprocess.check_output(
                [sys.executable, setup_runtime.SCRIPTS / "setup_runtime.py", "paths", "--shell", "bash"],
                env=dict(os.environ, **{profile_var: str(profile)}), encoding="utf-8")
            self.assertIn("中文", output)
            self.assertEqual(json.loads(output)["runtimeStatus"], "missing")

    def test_legacy_cleanup_targets_only_the_old_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            scripts = Path(temp).resolve() / "scripts"
            legacy = scripts / ".venv"
            legacy.mkdir(parents=True)
            (legacy / "pyvenv.cfg").write_text("home = old", encoding="utf-8")
            (scripts / "steering_linux.py").touch()
            (scripts / "steering_unix.py").touch()
            with patch.object(setup_runtime, "SCRIPTS", scripts):
                setup_runtime.clean_legacy()
            self.assertFalse(legacy.exists())
            self.assertFalse((scripts / "steering_linux.py").exists())
            self.assertTrue((scripts / "steering_unix.py").exists())
