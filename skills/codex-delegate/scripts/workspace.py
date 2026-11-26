"""Observe net Git worktree changes around a writable delegation."""
import os
from pathlib import Path
import subprocess


def git_executable():
    # Windows executable lookup can search the current directory before PATH.
    for entry in os.get_exec_path():
        directory = Path(entry.strip('"'))
        git = directory / "git.exe"
        if directory.is_absolute() and git.is_file():
            return git
    return None


def workspace_snapshot(cwd):
    git = git_executable()
    if git is None:
        return None
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    try:
        files = subprocess.run(
            [git, "-c", "core.fsmonitor=false", "ls-files", "-z", "--cached", "--others",
             "--exclude-standard", "--", "."],
            cwd=cwd, env=env, capture_output=True, check=True, timeout=10).stdout
        snapshot = {}
        for entry in files.split(b"\0")[:-1]:
            path = cwd / os.fsdecode(entry)
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            snapshot[path] = (info.st_mode, info.st_size, info.st_mtime_ns, info.st_ino)
        return snapshot
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def workspace_changes(cwd, before, patches):
    after = workspace_snapshot(cwd) if before is not None else None
    if after is None:
        return {"changeTracking": "sdk-patches"}
    paths = dict.fromkeys(os.path.normcase(os.path.abspath(cwd / path)) for path in patches)
    changed = list(patches)
    for path in sorted(before.keys() | after.keys()):
        if before.get(path) != after.get(path) and os.path.normcase(str(path)) not in paths:
            changed.append(os.path.relpath(path, cwd))
    return {"changedFiles": changed, "changeTracking": "sdk-patches-and-git-worktree"}
