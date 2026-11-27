"""Install and locate the Python runtime for an installed Codex skill."""
import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parent
REQUIREMENTS = SCRIPTS / "requirements.txt"
SUPPORTED_PLATFORMS = ("win32", "linux", "darwin")


def data_directory(home=None):
    return (Path.home() if home is None else home) / ".codex-delegate"


def scratch_root(home=None):
    return data_directory(home) / "scratch"


def path_status(path, matches):
    try:
        return "available" if matches(path.stat().st_mode) else "missing"
    except (FileNotFoundError, NotADirectoryError):
        return "missing"
    except PermissionError:
        return "inaccessible"


def runtime_location():
    name = f"venv-{sys.platform}"
    current = data_directory() / name
    status = path_status(current, stat.S_ISDIR)
    if status != "missing":
        python = current / python_relative_path()
        return current, path_status(python, stat.S_ISREG) if status == "available" else status
    legacy = Path.home() / ".gemini" / "config" / "codex-delegate-runtime" / name
    status = path_status(legacy / python_relative_path(), stat.S_ISREG)
    return (current, "missing") if status == "missing" else (legacy, status)


def python_relative_path():
    return "Scripts/python.exe" if sys.platform == "win32" else "bin/python"


def launcher_prefix(exe, runner, shell):
    if shell == "bash":
        return shlex.join([exe.as_posix(), runner.as_posix()])
    if shell == "cmd":
        return f'"{exe}" "{runner}"'
    command = str(exe)
    if not re.fullmatch(r"[A-Za-z]:[\\\w.\-]+", command):
        command = "& '" + command.replace("'", "''") + "'"
    runner = str(runner).replace("'", "''")
    return f"{command} '{runner}'"


def launchers(shell="auto"):
    env, status = runtime_location()
    python = env / python_relative_path()
    scripts = {"readOnly": SCRIPTS / "codex_ro.py", "workspaceWrite": SCRIPTS / "codex_rw.py"}
    supported = ["powershell", "bash", "cmd"] if sys.platform == "win32" else ["bash"]
    # Cmd expands percent variables even in quotes. Delayed expansion may also alter '!'.
    if "cmd" in supported and any(re.search(r"[%!]", str(path)) for path in (python, *scripts.values())):
        supported.remove("cmd")
    if shell != "auto" and shell not in supported:
        raise ValueError(f"{shell} is unavailable for this platform or path. Choose {', '.join(supported)}.")
    shells = {name: {key: launcher_prefix(python, script, name) for key, script in scripts.items()}
              for name in supported}
    selected = supported[0] if shell == "auto" else shell
    return {"python": str(python), "runtimeStatus": status,
            "runtimeExists": None if status == "inaccessible" else status == "available",
            "scratchRoot": str(scratch_root()), "shell": selected, "shells": shells, **shells[selected]}


def install():
    env, status = runtime_location()
    if status == "inaccessible":
        raise SystemExit(f"Runtime access denied at {env}. Request access through the host's approval mechanism.")
    data_directory().mkdir(mode=0o700, exist_ok=True)
    scratch_root().mkdir(mode=0o700, exist_ok=True)
    python = env / python_relative_path()
    if status == "missing":
        subprocess.run([sys.executable, "-m", "venv", env], check=True)
    subprocess.run([python, "-m", "pip", "--disable-pip-version-check", "install", "-r", REQUIREMENTS], check=True)


def check():
    env, status = runtime_location()
    if status == "inaccessible":
        raise SystemExit(f"Runtime access denied at {env}. Request access through the host's approval mechanism.")
    if status == "missing":
        raise SystemExit("Runtime missing. Run setup_runtime.py install first.")
    result = subprocess.run(
        [env / python_relative_path(), SCRIPTS / "codex_ro.py", "--action", "list", "--all", "--limit", "1"],
        stdout=subprocess.PIPE, encoding="utf-8", check=True,
    )
    if not isinstance(json.loads(result.stdout)["sessions"], list):
        raise SystemExit("Codex returned an invalid session list.")
    print("Installation verified.")


def clean_legacy():
    legacy = SCRIPTS / ".venv"
    if legacy.exists() or legacy.is_symlink():
        if legacy.resolve() != legacy or not (legacy / "pyvenv.cfg").is_file():
            raise ValueError(f"Expected a local virtual environment at {legacy}.")
        if Path(sys.prefix).resolve() == legacy:
            raise ValueError("Run cleanup from a Python interpreter outside scripts/.venv.")
        shutil.rmtree(legacy)
    (SCRIPTS / "steering_linux.py").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check", "paths"))
    parser.add_argument("--shell", choices=("auto", "powershell", "bash", "cmd"), default="auto",
                        help="select launcher quoting for paths")
    parser.add_argument("--clean-legacy", action="store_true",
                        help="after install succeeds, remove the old in-skill environment and Linux launcher")
    args = parser.parse_args()
    if sys.platform not in SUPPORTED_PLATFORMS or sys.version_info < (3, 10):
        parser.exit(1, "Use Windows, Linux, or macOS with Python 3.10 or later.\n")
    if args.clean_legacy and args.action != "install":
        parser.error("--clean-legacy requires install")
    if args.action == "paths":
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(launchers(args.shell), ensure_ascii=False))
        return
    if args.action == "install":
        install()
    check()
    if args.clean_legacy:
        clean_legacy()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except (OSError, ValueError) as error:
        sys.exit(str(error))
