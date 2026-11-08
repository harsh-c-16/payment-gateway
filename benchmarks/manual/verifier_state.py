"""Legacy milestone verifiers preserve pre-existing edits instead of requiring clean HEAD."""

import subprocess


class Preservation:
    def __init__(self, commands, root, out):
        guarded = next(c for c, _ in commands if c[:3] == ["git", "diff", "--exit-code"])
        guarded.remove("--exit-code")
        self.command = guarded
        self.before = subprocess.check_output(
            guarded,
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (out / "initial-protected.diff").write_text(self.before, encoding="utf-8")

    def matches(self, command, stdout):
        return command != self.command or stdout == self.before
