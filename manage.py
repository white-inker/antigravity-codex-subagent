"""Install and maintain the Antigravity Codex skill on Windows."""
import argparse
import json
import os
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
    SCRIPTS / "steering.py",
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
    if relative in (SKILL / "SKILL.md", SKILL / "references" / "usage.md"):
        scripts = (config / SCRIPTS).resolve()
        exe = str(scripts / ".venv" / "Scripts" / "python.exe").replace("'", "''")
        for suffix in ("ro", "rw"):
            runner = str(scripts / f"codex_{suffix}.py").replace("'", "''")
            data = data.replace(f"__CODEX_{suffix.upper()}__".encode(), f"& '{exe}' '{runner}'".encode("utf-8"))
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


def check(config, python):
    for relative in FILES:
        if not (config / relative).is_file():
            raise SystemExit(f"Missing {config / relative}. Run: python manage.py install")
    result = subprocess.run(
        [python, config / SCRIPTS / "codex_ro.py", "--action", "list", "--cwd", ROOT],
        cwd=ROOT, stdout=subprocess.PIPE, encoding="utf-8", check=True,
    )
    if not isinstance(json.loads(result.stdout)["sessions"], list):
        raise SystemExit("Codex returned an invalid session list.")
    print("Installation verified.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check", "update", "test"),
                        help="install the skill, verify the installation, pull and install updates, or run tests")
    action = parser.parse_args().action
    if sys.platform != "win32" or sys.version_info < (3, 10):
        parser.exit(1, "Use Windows with Python 3.10 or later.\n")
    config = Path(os.environ["USERPROFILE"]) / ".gemini" / "config"
    venv = config / SCRIPTS / ".venv"
    python = venv / "Scripts" / "python.exe"

    if action == "update":
        if not shutil.which("git"):
            parser.exit(1, "Git was not found on PATH. Install Git for Windows before running update.\n")
        subprocess.run(["git", "pull", "--ff-only"], cwd=ROOT, check=True)
        subprocess.run([sys.executable, ROOT / "manage.py", "install"], check=True)
        return
    if action == "install":
        if not python.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        else:
            # Earlier installs made with uv can have an interpreter without pip.
            subprocess.run([python, "-m", "ensurepip"], check=True)
        subprocess.run([python, "-m", "pip", "--disable-pip-version-check", "install",
                        "-r", ROOT / SCRIPTS / "requirements.txt"], check=True)
        for relative in FILES:
            deploy(relative, config)
        check(config, python)
        return
    if not python.is_file():
        parser.exit(1, "SDK environment missing. Run: python manage.py install\n")
    if action == "check":
        check(config, python)
    else:
        subprocess.run([python, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except OSError as error:
        sys.exit(str(error))
