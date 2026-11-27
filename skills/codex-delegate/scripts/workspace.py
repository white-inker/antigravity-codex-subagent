"""Observe net Git worktree changes around a writable delegation."""
import os
from pathlib import Path
import subprocess
from time import monotonic

MAX_SNAPSHOT_FILES = 10000
SNAPSHOT_TIMEOUT = 3


def git_executable():
    # Windows executable lookup can search the current directory before PATH.
    for entry in os.get_exec_path():
        directory = Path(entry.strip('"'))
        git = directory / ("git.exe" if os.name == "nt" else "git")
        if directory.is_absolute() and git.is_file() and os.access(git, os.X_OK):
            return git
    return None


def workspace_snapshot(cwd):
    git = git_executable()
    if git is None:
        return None, "git-not-available"
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    deadline = monotonic() + SNAPSHOT_TIMEOUT
    try:
        files = subprocess.run(
            [git, "-c", "core.fsmonitor=false", "ls-files", "-z", "--cached", "--others",
             "--exclude-standard", "--", "."],
            cwd=cwd, env=env, capture_output=True, check=True, timeout=SNAPSHOT_TIMEOUT).stdout
        if files.count(b"\0") > MAX_SNAPSHOT_FILES:
            return None, "snapshot-file-limit"
        snapshot = {}
        for entry in files.split(b"\0")[:-1]:
            if monotonic() >= deadline:
                return None, "snapshot-time-limit"
            path = cwd / os.fsdecode(entry)
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            snapshot[path] = (info.st_mode, info.st_size, info.st_mtime_ns, info.st_ino)
        return snapshot, None
    except subprocess.TimeoutExpired:
        return None, "snapshot-time-limit"
    except subprocess.CalledProcessError:
        return None, "git-list-failed"
    except OSError:
        return None, "snapshot-io-error"


def workspace_changes(cwd, before, patches):
    if before is None:
        return {"changeTracking": "sdk-patches"}
    original, reason = before
    if reason is not None:
        return {"changeTracking": "sdk-patches", "changeTrackingReason": reason}
    after, reason = workspace_snapshot(cwd)
    if reason is not None:
        return {"changeTracking": "sdk-patches", "changeTrackingReason": reason}
    changed = {}
    for path in patches:
        changed.setdefault(os.path.normcase(os.path.realpath(cwd / path)), path)
    for path in sorted(original.keys() | after.keys()):
        if original.get(path) != after.get(path):
            changed.setdefault(os.path.normcase(os.path.realpath(path)), os.path.relpath(path, cwd))
    return {"changedFiles": list(changed.values()), "changeTracking": "sdk-patches-and-git-worktree"}
