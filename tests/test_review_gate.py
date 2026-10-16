"""Which Bash commands review_gate.py treats as opening a PR.

Run: python3 -m unittest discover tests

The gate fails closed: a missed real `gh pr create` lets an unreviewed PR
through, a false match only costs a denial. So RUNS is the list that must
never shrink; SKIPS holds the everyday mentions the gate exists to let pass.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HOOKS))
from review_gate import _pr_create_args  # noqa: E402

G = "gh pr " + "create"  # split so this file's own text never trips a gate

RUNS = {
    "plain": f"{G} --base main --title x",
    "after push, body heredoc": f"git push -u origin b 2>&1 | tail -2 && {G} --base main --body-file - <<'EOF'\nbody mentions {G}\nEOF",
    "cd first": f"cd /tmp/x && {G} -B dev",
    "env prefix": f"GH_TOKEN=abc {G} --base=main",
    "after newline": f"echo hi\n{G} --base main",
    "after a heredoc": f"git commit -F - <<'EOF'\nmsg\nEOF\n{G} --base main",
    "bash -c": f"bash -c '{G} --base main'",
    "bash -lc": f"bash -lc '{G} --base main'",
    "bash -o pipefail -c": f"bash -o pipefail -c '{G} --base main'",
    "bash --login -c": f"bash --login -c '{G} --base main'",
    "/bin/bash -c": f"/bin/bash -c '{G} --base main'",
    "eval": f"eval {G} --base main",
    "substitution": f"url=$({G} --base main --fill)",
    "substitution in dq": f'URL="$({G} --base main --fill)"',
    "nested quotes in dq substitution": f'PR="$(cd "$R" && {G} --base main --fill)"',
    "backticks": f"`{G} --fill`",
    "subshell": f"( {G} )",
    "if/then": f"if git push; then {G} --base main; fi",
    "for/do": f"for b in x; do {G} --head $b; done",
    "timeout wrapper": f"timeout 30 {G} -R o/r --base dev",
    "absolute path": f"/opt/homebrew/bin/{G} --base main",
    "quoted gh": '"gh" pr ' + "create --base main",
    "gh pr new alias": "gh pr new --base main --fill",
    "gh.exe": "gh.exe pr " + "create --base main",
    "heredoc piped to bash": f"cat <<'EOF' | bash\n{G} --base main\nEOF",
    "python heredoc": f"python3 - <<'EOF'\nimport subprocess\nsubprocess.run('{G} --fill', shell=True)\nEOF",
    "python -c": f"python3 -c \"import os; os.system('{G} --fill')\"",
    "script written then run": f"cat > /tmp/pr.sh <<'EOF'\n{G} --fill\nEOF\nbash /tmp/pr.sh",
    "script run by path": f"cat > pr.sh <<'EOF'\n{G} --fill\nEOF\n./pr.sh",
    "variable as command": f"CMD='{G} --fill'; $CMD",
    "here-string is not a heredoc": f'cat <<< "EOF"\n{G} --base main',
    "arithmetic shift is not a heredoc": f"echo $((1<<2))\n{G} --base main",
    "comment with apostrophe": f"git push -u origin HEAD  # don't forget\n{G} --title 'Fix gate' --base main",
    "comment with heredoc operator": f"git push # body via <<EOF later\n{G} --base main --fill\nEOF",
    "ANSI-C quote with escaped quote": f"echo $'don\\'t'; {G} --base main; echo 'x'",
    "unterminated quote": f"echo 'unbalanced && {G}",
    "awk system()": f"awk 'BEGIN{{system(\"{G} --fill\")}}'",
    "make recipe": f"make -f - <<'EOF'\npr:\n\t{G} --fill\nEOF",
    "trap": f"trap '{G} --fill' EXIT; git push",
    "xargs sh -c": f"echo b | xargs -I{{}} sh -c '{G} --head {{}}'",
    "git alias": f"git -c alias.p='!{G} --fill' p",
    "backticks in dq": f'X="`{G} --fill`"',
    "quoted $SHELL -c": f'"$SHELL" -c \'{G} --base main\'',
    "piped to quoted $SHELL": f'echo \'{G} --fill\' | "$SHELL"',
    "quoted shell path": f'"/bin/bash" -c \'{G} --base main\'',
    "single-quoted bash": f"'bash' -c '{G} --base main'",
    "git rebase --exec": f"git rebase -x '{G} --fill' main",
    "pwsh -c": f"pwsh -c '{G} --fill'",
    "VAR=value then quoted bash": f"x=1 \"bash\" -c '{G} --base main'",
}

SKIPS = {
    "commit -m": f"git commit -m 'allow {G} again'",
    "commit -m with apostrophe": f"git commit -m \"don't allow {G} yet\"",
    "commit -F heredoc": f"git commit -q -F - <<'EOF'\nreview_gate then allowed {G}\nEOF",
    "commit -F unquoted heredoc": f"git commit -F - <<EOF\nthen {G}\nEOF",
    "heredoc message with apostrophe": f"git commit -F - <<'EOF'\nDon't allow {G} yet\nEOF",
    "apostrophe on a later line": f"git commit -F - <<'EOF'\nGate: allow {G}\n\nIt's fine.\nEOF",
    "quoted string in a written file": f"cat > f.py <<'EOF'\nPR='{G}'\nEOF",
    "multi-line -m with apostrophes": f"git commit -m \"Gate: allow {G}\n\nIt's fine, isn't it\"",
    "file written by heredoc": f"cat > notes.md <<'EOF'\nrun {G} later\nEOF",
    "grep": f"grep -rn '{G}' hooks/",
    "echo dq": f'echo "{G}"',
    "other gh pr command": "gh pr view 3",
    "nothing": "ls",
    "comment without later quotes": "git add -A # stage it's all\ngit commit -m 'x'",
    "runner words only inside the message": f"git commit -m 'open source env: {G}'",
}

BASES = {
    f"{G} --base dev": "dev",
    f"{G} -B dev --fill": "dev",
    f"{G} --base=dev": "dev",
    f"{G} --title Fix#12 --base dev": "dev",
    f"bash -c '{G} --base dev'": "dev",
}


class Detection(unittest.TestCase):
    def test_real_invocations_count(self):
        for name, command in RUNS.items():
            with self.subTest(name):
                self.assertIsNotNone(_pr_create_args(command), command)

    def test_inert_mentions_pass(self):
        for name, command in SKIPS.items():
            with self.subTest(name):
                self.assertIsNone(_pr_create_args(command), command)


class EndToEnd(unittest.TestCase):
    """The hook as Claude Code runs it, in a scratch repo with no review."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "w"

        def git(*args, cwd=root):
            subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

        git("init", "-q", "--bare", "origin.git")
        git("init", "-q", "-b", "main", "w")
        ident = ["-c", "user.email=t@example.com", "-c", "user.name=t"]
        git(*ident, "commit", "-q", "--allow-empty", "-m", "init", cwd=self.repo)
        git("remote", "add", "origin", str(root / "origin.git"), cwd=self.repo)
        git("push", "-q", "-u", "origin", "main", cwd=self.repo)
        git("remote", "set-head", "origin", "main", cwd=self.repo)
        git("switch", "-q", "-c", "feat", cwd=self.repo)
        (self.repo / "f").write_text("x\n")

    def tearDown(self):
        self.tmp.cleanup()

    def gate(self, command: str) -> str:
        event = {"tool_name": "Bash", "cwd": str(self.repo), "tool_input": {"command": command}}
        out = subprocess.run(
            [sys.executable, str(HOOKS / "review_gate.py")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            check=True,
        )
        return "deny" if '"deny"' in out.stdout else "allow"

    def test_unreviewed_pr_is_denied(self):
        self.assertEqual(self.gate(f"git push && {G} --base main"), "deny")

    def test_base_is_read_from_the_invocation(self):
        from review_gate import _repo_and_base

        for command, base in BASES.items():
            with self.subTest(command):
                _, got = _repo_and_base(command, _pr_create_args(command), self.repo)
                self.assertEqual(got, f"origin/{base}")

    def test_commit_message_naming_it_is_allowed(self):
        self.assertEqual(self.gate(f"git commit -F - <<'EOF'\nthen {G}\nEOF"), "allow")


if __name__ == "__main__":
    unittest.main()
