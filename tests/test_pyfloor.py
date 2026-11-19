"""The Python floor for the hooks: `hooks/pyfloor.py` and every hook entry
point that calls it first, so an old `python3` on the PATH fails loudly
(the guard blocks, other hooks warn) instead of crashing at import, which
Claude Code treats as a non-blocking error and leaves the guard silently off.

Run: /opt/homebrew/bin/python3.13 -m pytest tests/test_pyfloor.py

The 3.9 run tests execute the real scripts under /usr/bin/python3 when it
exists and is older than 3.12 (they skip otherwise). Everything runs in
temp directories; no network.
"""

import ast
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HOOKS))

CLOSED = ("guard.py", "review_gate.py")
OPEN = ("decision_delivery.py", "stop_tests.py", "agent_usage.py", "review_record.py")
ENTRY_POINTS = CLOSED + OPEN + ("decisions.py",)
OLD = Path("/usr/bin/python3")


def old_python():
    """(path, executable, (major, minor)) of an interpreter below 3.12, or None."""
    if not OLD.exists():
        return None
    try:
        out = subprocess.run(
            [str(OLD), "-c", "import sys; print(sys.executable); print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True, text=True, timeout=30,
        )
        exe, ver = out.stdout.split("\n")[:2]
        major, minor = (int(x) for x in ver.split())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return (str(OLD), exe, (major, minor)) if (major, minor) < (3, 12) else None


def fake_version(major, minor, micro):
    # sys.version_info's type can't be instantiated; a plain tuple compares the same way
    return (major, minor, micro, "final", 0)


def sentence(name, version, executable):
    return (
        f"{name} needs Python 3.12 or newer; found {version} at {executable}. "
        "Put a newer python3 first on the PATH Claude Code runs hooks with (docs/hooks.md)."
    )


def import_pyfloor():
    import pyfloor

    return pyfloor


class Check(unittest.TestCase):
    def run_check(self, mode, version=(3, 9, 6)):
        pyfloor = import_pyfloor()
        out, err = io.StringIO(), io.StringIO()
        code = "returned"
        with mock.patch.object(sys, "version_info", fake_version(*version)), \
                mock.patch.object(sys, "executable", "/opt/odd/python3"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                pyfloor.check(mode, "acme-hook")
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def test_minimum_is_3_12(self):
        self.assertEqual(import_pyfloor().MIN, (3, 12))

    def test_new_enough_python_returns_silently_in_every_mode(self):
        for mode in ("closed", "open", "text"):
            for version in ((3, 12, 0), (3, 13, 1), (4, 0, 0)):
                with self.subTest(mode=mode, version=version):
                    self.assertEqual(self.run_check(mode, version), ("returned", "", ""))

    def test_closed_blocks_with_the_sentence_on_stderr(self):
        code, out, err = self.run_check("closed")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(err.strip(), sentence("acme-hook", "3.9.6", "/opt/odd/python3"))

    def test_open_warns_with_a_system_message_and_exits_0(self):
        code, out, err = self.run_check("open")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(
            json.loads(out), {"systemMessage": sentence("acme-hook", "3.9.6", "/opt/odd/python3")}
        )

    def test_text_prints_the_sentence_as_plain_text_and_exits_0(self):
        code, out, err = self.run_check("text")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out.strip(), sentence("acme-hook", "3.9.6", "/opt/odd/python3"))

    def test_message_names_the_found_version_and_interpreter(self):
        _, _, err = self.run_check("closed", (3, 11, 4))
        self.assertIn("found 3.11.4 at /opt/odd/python3", err)

    def test_just_below_the_floor_is_refused(self):
        code, _, _ = self.run_check("closed", (3, 11, 99))
        self.assertEqual(code, 2)


class Source(unittest.TestCase):
    def test_pyfloor_uses_only_old_syntax(self):
        text = (HOOKS / "pyfloor.py").read_text()
        tree = ast.parse(text, feature_version=(3, 7))
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, (ast.NamedExpr, ast.Match), ast.dump(node)[:60])
            ann = [getattr(node, "returns", None), getattr(node, "annotation", None)]
            for a in ann:
                if a is not None:
                    self.assertFalse(
                        any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)
                            for n in ast.walk(a)),
                        "no `X | Y` annotations in pyfloor.py",
                    )
        self.assertNotRegex(text, r"\{[^{}'\"]*=\}")  # no f-string `=`

    def local_modules(self):
        return {p.stem for p in HOOKS.glob("*.py")} - {"pyfloor"}

    def test_each_entry_point_calls_pyfloor_before_any_other_local_import(self):
        local = self.local_modules()
        for name in ENTRY_POINTS:
            with self.subTest(entry=name):
                lines = (HOOKS / name).read_text().splitlines()
                self_stem = Path(name).stem
                imp = next((i for i, ln in enumerate(lines)
                            if re.match(r"\s*import pyfloor\b", ln)), None)
                self.assertIsNotNone(imp, f"{name} never imports pyfloor")
                call = next((i for i, ln in enumerate(lines)
                             if re.match(r"\s*pyfloor\.check\(", ln)), None)
                self.assertIsNotNone(call, f"{name} never calls pyfloor.check")
                self.assertLess(imp, call)
                for i, ln in enumerate(lines):
                    m = re.match(r"\s*(?:from|import)\s+(\w+)", ln)
                    if m and m.group(1) in local and m.group(1) != self_stem:
                        self.assertGreater(i, call, f"{name}:{i + 1} imports {m.group(1)} before the floor check")
                    self.assertFalse(
                        re.match(r"\s*(def|class)\s", ln) and i < call,
                        f"{name}:{i + 1} defines something before the floor check",
                    )

    def test_each_entry_point_uses_its_mode(self):
        for name in CLOSED:
            with self.subTest(entry=name):
                self.assertRegex((HOOKS / name).read_text(), r"pyfloor\.check\(\s*[\"']closed[\"']")
        for name in OPEN:
            with self.subTest(entry=name):
                self.assertRegex((HOOKS / name).read_text(), r"pyfloor\.check\(\s*[\"']open[\"']")

    def test_codex_adapter_checks_the_floor(self):
        text = (ROOT / "codex" / "hook_adapter.py").read_text()
        self.assertIn("pyfloor", text)


@unittest.skipUnless(old_python(), "needs /usr/bin/python3 older than 3.12")
class UnderOldPython(unittest.TestCase):
    def setUp(self):
        self.py, self.exe, self.ver = old_python()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name).resolve() / "acme"
        (self.project / ".claude").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        (self.project / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": ["docs/decisions"]})
        )
        self.home = Path(tmp.name) / "home"
        self.home.mkdir()

    def run_script(self, script, *args, event=None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project), HOME=str(self.home),
                   PYTHONDONTWRITEBYTECODE="1")
        event = event if event is not None else {
            "hook_event_name": "PreToolUse", "session_id": "s1", "cwd": str(self.project),
            "tool_name": "Bash", "tool_input": {"command": "ls"},
        }
        return subprocess.run(
            [self.py, str(script), *args], input=json.dumps(event), capture_output=True,
            text=True, env=env, cwd=str(self.project), timeout=60,
        )

    def test_every_entry_point_parses_under_the_old_grammar(self):
        for name in ENTRY_POINTS + ("pyfloor.py",):
            with self.subTest(entry=name):
                done = subprocess.run(
                    [self.py, "-c", "import ast,sys; ast.parse(open(sys.argv[1]).read())",
                     str(HOOKS / name)], capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
        done = subprocess.run(
            [self.py, "-c", "import ast,sys; ast.parse(open(sys.argv[1]).read())",
             str(ROOT / "codex" / "hook_adapter.py")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_guard_and_review_gate_block_with_exit_2_and_the_sentence(self):
        for name in CLOSED:
            with self.subTest(hook=name):
                proc = self.run_script(HOOKS / name)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIn("needs Python 3.12 or newer; found ", proc.stderr)
                self.assertIn(f"at {self.exe}.", proc.stderr)
                self.assertIn("Put a newer python3 first on the PATH Claude Code runs hooks with (docs/hooks.md).",
                              proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)

    def test_open_hooks_warn_and_exit_0(self):
        for name in OPEN:
            with self.subTest(hook=name):
                proc = self.run_script(HOOKS / name)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                message = json.loads(proc.stdout)["systemMessage"]
                self.assertIn("needs Python 3.12 or newer; found ", message)
                self.assertIn(f"at {self.exe}.", message)
                self.assertNotIn("Traceback", proc.stderr)

    def test_decisions_session_start_prints_the_sentence_as_text(self):
        proc = self.run_script(HOOKS / "decisions.py", "session-start",
                               event={"hook_event_name": "SessionStart", "session_id": "s1",
                                      "source": "startup"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("needs Python 3.12 or newer; found ", proc.stdout)
        with self.assertRaises(ValueError):
            json.loads(proc.stdout)  # plain text, not JSON

    def test_decisions_subagent_start_carries_the_sentence_as_additional_context(self):
        proc = self.run_script(HOOKS / "decisions.py", "subagent-start",
                               event={"hook_event_name": "SubagentStart", "session_id": "s1",
                                      "agent_id": "a1"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SubagentStart")
        self.assertIn("needs Python 3.12 or newer; found ", out["additionalContext"])

    def test_decisions_cli_subcommands_fail_with_exit_2_on_stderr(self):
        for args in (("index",), ("lint",), ("resolve", "--path", "x")):
            with self.subTest(args=args):
                proc = self.run_script(HOOKS / "decisions.py", *args)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIn("needs Python 3.12 or newer; found ", proc.stderr)
                self.assertEqual(proc.stdout, "")

    def test_codex_adapter_denies_a_tool_call_and_warns_on_other_events(self):
        adapter = ROOT / "codex" / "hook_adapter.py"
        proc = self.run_script(adapter)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("needs Python 3.12 or newer; found ", out["permissionDecisionReason"])
        for kind in ("Stop", "PostToolUse", "SessionStart"):
            with self.subTest(event=kind):
                proc = self.run_script(adapter, event={"hook_event_name": kind, "session_id": "s1",
                                                       "cwd": str(self.project)})
                self.assertEqual(proc.returncode, 0, proc.stderr)
                out = json.loads(proc.stdout)
                self.assertNotIn("decision", out)  # not a block
                self.assertIn("needs Python 3.12 or newer; found ", out["systemMessage"])


if __name__ == "__main__":
    unittest.main()
