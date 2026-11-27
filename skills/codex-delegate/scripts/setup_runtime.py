"""Install and locate the Python runtime for an installed Codex skill."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parent
REQUIREMENTS = SCRIPTS / "requirements.txt"
SUPPORTED_PLATFORMS = ("win32", "linux", "darwin")


def data_directory():
    return Path.home().resolve() / ".codex-delegate"


def scratch_root():
    return data_directory() / "scratch"


def runtime_env():
    name = f"venv-{sys.platform}"
    current = data_directory() / name
    legacy = Path.home() / ".gemini" / "config" / "codex-delegate-runtime" / name
    if current.exists() or not (legacy / python_relative_path()).is_file():
        return current
    return legacy


def python_relative_path():
    return "Scripts/python.exe" if sys.platform == "win32" else "bin/python"


def runtime_python():
    return runtime_env() / python_relative_path()


def launcher_prefix(exe, runner):
    if sys.platform != "win32":
        return shlex.join([str(exe), str(runner)])
    command = str(exe)
    if not re.fullmatch(r"[A-Za-z]:[\\\w.\-]+", command):
        command = "& '" + command.replace("'", "''") + "'"
    runner = str(runner).replace("'", "''")
    return f"{command} '{runner}'"


def launchers():
    python = runtime_python()
    return {"python": str(python), "runtimeExists": python.is_file(),
            "scratchRoot": str(scratch_root()),
            "readOnly": launcher_prefix(python, SCRIPTS / "codex_ro.py"),
            "workspaceWrite": launcher_prefix(python, SCRIPTS / "codex_rw.py")}


def install():
    data_directory().mkdir(mode=0o700, exist_ok=True)
    scratch_root().mkdir(mode=0o700, exist_ok=True)
    python = runtime_python()
    if not python.is_file():
        subprocess.run([sys.executable, "-m", "venv", runtime_env()], check=True)
    subprocess.run([python, "-m", "pip", "--disable-pip-version-check", "install", "-r", REQUIREMENTS], check=True)


def check():
    python = runtime_python()
    if not python.is_file():
        raise SystemExit("Runtime missing. Run setup_runtime.py install first.")
    result = subprocess.run(
        [python, SCRIPTS / "codex_ro.py", "--action", "list", "--all", "--limit", "1"],
        stdout=subprocess.PIPE, encoding="utf-8", check=True,
    )
    if not isinstance(json.loads(result.stdout)["sessions"], list):
        raise SystemExit("Codex returned an invalid session list.")
    print("Installation verified.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check", "paths"))
    action = parser.parse_args().action
    if sys.platform not in SUPPORTED_PLATFORMS or sys.version_info < (3, 10):
        parser.exit(1, "Use Windows, Linux, or macOS with Python 3.10 or later.\n")
    if action == "paths":
        print(json.dumps(launchers(), ensure_ascii=True))
        return
    if action == "install":
        install()
    check()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except OSError as error:
        sys.exit(str(error))
