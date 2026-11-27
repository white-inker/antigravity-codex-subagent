"""History and read-only Codex turns."""
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True
    from codex import cli

    cli("read-only")
