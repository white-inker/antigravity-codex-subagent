"""Initialize and test the Codex Delegate runtime from a repository checkout."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SKILL = Path("skills/codex-delegate")
SCRIPTS = SKILL / "scripts"
SETUP = ROOT / SCRIPTS / "setup_runtime.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check", "update", "test"),
                        help="initialize the runtime, verify it, update the checkout, or run tests")
    action = parser.parse_args().action
    if sys.platform not in ("win32", "linux", "darwin") or sys.version_info < (3, 10):
        parser.exit(1, "Use Windows, Linux, or macOS with Python 3.10 or later.\n")
    if action == "update":
        if not shutil.which("git"):
            parser.exit(1, "Git was not found on PATH. Install Git before running update.\n")
        subprocess.run(["git", "pull", "--ff-only"], cwd=ROOT, check=True)
        action = "install"
    if action in ("install", "check"):
        subprocess.run([sys.executable, SETUP, action], cwd=ROOT, check=True)
    else:
        paths = subprocess.check_output([sys.executable, SETUP, "paths"], encoding="utf-8")
        runtime = json.loads(paths)
        if runtime["runtimeStatus"] == "inaccessible":
            parser.exit(1, "SDK runtime access denied. Run the tests from a terminal with approved access.\n")
        if runtime["runtimeStatus"] == "missing":
            parser.exit(1, "SDK runtime missing. Run: python manage.py install\n")
        subprocess.run([runtime["python"], "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except OSError as error:
        sys.exit(str(error))
