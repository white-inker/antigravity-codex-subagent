"""Install and maintain the Antigravity Codex skill from a repository checkout."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parent
SKILL = Path("skills/codex-delegate")
SCRIPTS = SKILL / "scripts"
FILES = (
    SCRIPTS / "requirements.txt",
    SCRIPTS / "setup_runtime.py",
    SCRIPTS / "steering.py",
    SCRIPTS / "steering_windows.py",
    SCRIPTS / "steering_linux.py",
    SCRIPTS / "codex.py",
    SCRIPTS / "codex_ro.py",
    SCRIPTS / "codex_rw.py",
    SCRIPTS / "workspace.py",
    SKILL / "SKILL.md",
    SKILL / "references" / "usage.md",
    Path("agents/codex.md"),
)


def deploy(relative, config):
    destination = config / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = (ROOT / relative).read_bytes()
    if destination.is_file() and destination.read_bytes() == data:
        return
    # Publish a complete file even if another Antigravity window is reading it.
    pending = NamedTemporaryFile(dir=destination.parent, delete=False)
    temporary = Path(pending.name)
    try:
        with pending:
            pending.write(data)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def check(config):
    for relative in FILES:
        if not (config / relative).is_file():
            raise SystemExit(f"Missing {config / relative}. Run: python manage.py install")
    subprocess.run([sys.executable, config / SCRIPTS / "setup_runtime.py", "check"], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check", "update", "test"),
                        help="install the skill, verify the installation, pull and install updates, or run tests")
    action = parser.parse_args().action
    if sys.platform not in ("win32", "linux") or sys.version_info < (3, 10):
        parser.exit(1, "Use Windows or Linux with Python 3.10 or later.\n")
    config = Path.home() / ".gemini" / "config"

    if action == "update":
        if not shutil.which("git"):
            parser.exit(1, "Git was not found on PATH. Install Git before running update.\n")
        subprocess.run(["git", "pull", "--ff-only"], cwd=ROOT, check=True)
        subprocess.run([sys.executable, ROOT / "manage.py", "install"], check=True)
        return
    if action == "install":
        subprocess.run([sys.executable, ROOT / SCRIPTS / "setup_runtime.py", "install"], cwd=ROOT, check=True)
        for relative in FILES:
            deploy(relative, config)
        check(config)
        return
    if action == "check":
        check(config)
    else:
        paths = subprocess.check_output([sys.executable, ROOT / SCRIPTS / "setup_runtime.py", "paths"], encoding="utf-8")
        python = Path(json.loads(paths)["python"])
        if not python.is_file():
            parser.exit(1, "SDK runtime missing. Run: python manage.py install\n")
        subprocess.run([python, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except OSError as error:
        sys.exit(str(error))
