"""Workspace-write Codex turns and their live controls."""
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True
    from codex import cli

    cli("workspace-write")
