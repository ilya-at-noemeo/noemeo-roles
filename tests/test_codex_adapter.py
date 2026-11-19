"""Codex boundary regressions; no cloud calls, paid APIs or developer data."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "codex" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load("hook_adapter")
installer = load("install")


class CodexAdapterTest(unittest.TestCase):
    def test_patch_cannot_edit_or_move_to_secrets(self):
        for operation in ("Add File", "Update File", "Delete File", "Move to"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                result = adapter.dispatch({"hook_event_name": "PreToolUse", "cwd": tmp,
                    "tool_name": "apply_patch", "tool_input": {"command":
                    f"*** Begin Patch\n*** {operation}: .env\n*** End Patch"}})
                self.assertTrue(adapter.denied(result))

    def test_raw_exec_uses_target_repository_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            (target / ".claude").mkdir(parents=True)
            (target / ".claude/noemeo-guard.json").write_text('{"secrets": ["local.token"]}')
            result = adapter.dispatch({"hook_event_name": "PreToolUse", "cwd": tmp,
                "tool_name": "exec_command", "tool_input": {
                "cmd": "cat local.token", "workdir": str(target)}})
            self.assertTrue(adapter.denied(result))

    def test_shell_policy_and_harmless_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            for command in ("rm -rf sandbox", "git push --force origin topic"):
                self.assertTrue(adapter.denied(adapter.dispatch({
                    "hook_event_name": "PreToolUse", "cwd": tmp,
                    "tool_name": "Bash", "tool_input": {"command": command}})))
            self.assertIsNone(adapter.dispatch({"hook_event_name": "PreToolUse",
                "cwd": tmp, "tool_name": "Bash", "tool_input": {"command": "git status --short"}}))

    def test_only_named_reviewer_with_report_records(self):
        with patch.object(adapter, "run") as run:
            event = {"hook_event_name": "SubagentStop", "cwd": "/tmp",
                     "agent_type": "noemeo-test-engineer", "last_assistant_message": "Ready"}
            adapter.dispatch(event)
            run.assert_not_called()
            adapter.dispatch({**event, "agent_type": "noemeo-code-reviewer", "last_assistant_message": ""})
            run.assert_not_called()
            adapter.dispatch({**event, "agent_type": "noemeo-code-reviewer"})
            self.assertEqual(run.call_args.args[0], "review_record.py")
            self.assertIsNone(run.call_args.args[1]["transcript_path"])

    def test_hook_error_explicitly_denies_before_tool_use(self):
        event = {"hook_event_name": "PreToolUse", "cwd": "/missing/noemeo-fixture",
                 "tool_name": "Bash", "tool_input": {"command": "git status"}}
        result = subprocess.run([sys.executable, str(ROOT / "codex/hook_adapter.py")],
            input=json.dumps(event), text=True, capture_output=True, check=True)
        self.assertTrue(adapter.denied(json.loads(result.stdout)))

    def test_review_gate_survives_tool_switch_and_invalidates_edits(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as logdir, patch.dict(
            os.environ, {"NOEMEO_REVIEW_RECORD_LOG": str(Path(logdir) / "record.log")}
        ):
            repo = Path(tmp)
            def git(*args):
                subprocess.run(["git", "-C", tmp, *args], check=True, capture_output=True)
            git("init", "-b", "main")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (repo / "file.txt").write_text("baseline\n")
            git("add", "file.txt")
            git("commit", "-m", "baseline")
            git("update-ref", "refs/remotes/origin/main", "HEAD")
            (repo / "file.txt").write_text("reviewed change\n")
            event = {"hook_event_name": "PreToolUse", "cwd": tmp,
                "tool_name": "Bash", "tool_input": {"command": "gh pr create --base main --title fixture --body fixture"}}
            self.assertTrue(adapter.denied(adapter.dispatch(event)))
            adapter.dispatch({"hook_event_name": "SubagentStop", "cwd": tmp,
                "agent_type": "noemeo-code-reviewer", "last_assistant_message": f"Ready -- {tmp}, branch main against origin/main\nVerified fixture."})
            self.assertFalse(adapter.denied(adapter.dispatch(event)))
            (repo / "file.txt").write_text("later unreviewed change\n")
            self.assertTrue(adapter.denied(adapter.dispatch(event)))

    def test_patch_lint_uses_absolute_paths(self):
        with patch.object(adapter, "run", return_value=None) as run:
            adapter.dispatch({"hook_event_name": "PostToolUse", "cwd": "/tmp",
                "tool_name": "apply_patch", "tool_input": {
                "command": "*** Update File: nested/file.py\n"}})
            self.assertEqual(run.call_args.args[1]["tool_input"]["file_path"], "/private/tmp/nested/file.py" if Path('/tmp').resolve() == Path('/private/tmp') else "/tmp/nested/file.py")


FAKE_RUFF = """#!/usr/bin/env bash
# Stands in for ruff: `check` reports one problem it cannot fix, `format` is a no-op.
if [ "$1" = "check" ]; then echo "src/a.py:1:1: E999 invented problem"; exit 1; fi
exit 0
"""


class CodexDecisionsTest(unittest.TestCase):
    """Decision delivery through the adapter, on recorded Codex events."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / "acme"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        (self.project / ".claude").mkdir()
        (self.project / ".claude/noemeo-guard.json").write_text(
            json.dumps({"decision_roots": ["docs/decisions"]}))

    def decision(self, id, text, *, binding=True, **scope):
        path = self.project / f"docs/decisions/{id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = {"id": id, "kind": "policy", "status": "accepted",
                  "binding": "true" if binding else "false",
                  "summary": f"Summary of {id}", **{
                      k: "[" + ", ".join(f'"{x}"' for x in v) + "]" if isinstance(v, list) else v
                      for k, v in scope.items()}}
        front = "\n".join(f"{k}: {v}" for k, v in fields.items())
        path.write_text(f"---\n{front}\n---\n# Record {id}\n\n## How to apply\n{text}\n")

    def event(self, kind, tool, tool_input, session="s1"):
        return {"hook_event_name": kind, "session_id": session, "cwd": str(self.project),
                "tool_name": tool, "tool_input": tool_input}

    def pre(self, tool, tool_input, **kw):
        return adapter.dispatch(self.event("PreToolUse", tool, tool_input, **kw))

    def post(self, tool, tool_input, **kw):
        return adapter.dispatch(self.event("PostToolUse", tool, tool_input, **kw))

    @staticmethod
    def patch(*paths):
        return {"command": "*** Begin Patch\n" + "".join(
            f"*** Update File: {p}\n@@\n-a\n+b\n" for p in paths) + "*** End Patch"}

    @staticmethod
    def reason(output):
        output = output or {}
        return (output.get("hookSpecificOutput", {}).get("permissionDecisionReason")
                or output.get("reason") or "")

    def install_fake_ruff(self):
        (self.project / "pyproject.toml").write_text("[tool.ruff]\n")
        ruff = self.project / ".venv/bin/ruff"
        ruff.parent.mkdir(parents=True)
        ruff.write_text(FAKE_RUFF)
        ruff.chmod(0o755)
        (self.project / "src").mkdir(exist_ok=True)
        (self.project / "src/a.py").write_text("x = 1\n")

    def test_apply_patch_in_binding_scope_is_denied_once(self):
        self.decision("acme-0001", "Keep widgets sorted.", paths=["src/**"])
        output = self.pre("apply_patch", self.patch("src/a.py"))
        self.assertTrue(adapter.denied(output))
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertIn("acme-0001", self.reason(output))
        self.assertIn("Keep widgets sorted.", self.reason(output))
        self.assertFalse(adapter.denied(self.pre("apply_patch", self.patch("src/a.py"))))
        # Another session has not seen it yet.
        self.assertTrue(adapter.denied(self.pre("apply_patch", self.patch("src/a.py"), session="s2")))

    def test_apply_patch_is_checked_once_per_patched_path(self):
        self.decision("acme-0001", "Keep widgets sorted.", paths=["src/**"])
        self.assertTrue(adapter.denied(self.pre("apply_patch", self.patch("docs/readme.md", "src/a.py"))))
        self.assertIsNone(self.pre("apply_patch", self.patch("docs/readme.md")))

    def test_apply_patch_outside_scope_passes(self):
        self.decision("acme-0001", "Keep widgets sorted.", paths=["src/**"])
        self.assertIsNone(self.pre("apply_patch", self.patch("docs/readme.md")))

    def test_edit_tools_are_denied_once_and_share_delivery(self):
        self.decision("acme-0001", "Keep widgets sorted.", paths=["src/**"])
        target = str(self.project / "src/a.py")
        self.assertTrue(adapter.denied(self.pre("Edit", {"file_path": target})))
        for tool in ("Write", "Edit", "MultiEdit"):
            with self.subTest(tool=tool):
                self.assertFalse(adapter.denied(self.pre(tool, {"file_path": target})))

    def test_shell_command_in_scope_is_denied_once(self):
        self.decision("acme-0002", "Name the acme profile.", commands=["acme-cli *"])
        output = self.pre("Bash", {"command": "acme-cli sync --all"})
        self.assertTrue(adapter.denied(output))
        self.assertIn("Name the acme profile.", self.reason(output))
        self.assertFalse(adapter.denied(self.pre("Bash", {"command": "acme-cli sync --all"})))
        # The raw Codex name takes the same route.
        self.decision("acme-0003", "Mind the widget.", commands=["widget-cli *"])
        self.assertTrue(adapter.denied(self.pre("exec_command", {"cmd": "widget-cli run"})))

    def test_shell_command_outside_scope_passes(self):
        self.decision("acme-0002", "Name the acme profile.", commands=["acme-cli *"])
        self.assertIsNone(self.pre("Bash", {"command": "git status --short"}))

    def test_delivery_runs_after_guard_and_before_review_gate(self):
        self.decision("acme-0002", "Name the acme profile.", commands=["acme-cli *"])
        calls = []
        real = adapter.run

        def spy(name, *args, **kw):
            calls.append(name)
            return real(name, *args, **kw)

        with patch.object(adapter, "run", spy):
            self.pre("Bash", {"command": "acme-cli sync"})  # denied by delivery
            self.assertNotIn("review_gate.py", calls)
            calls.clear()
            self.pre("Bash", {"command": "acme-cli sync"})  # delivered, so on to the gate
        self.assertIn("decision_delivery.py", calls)
        self.assertLess(calls.index("guard.py"), calls.index("decision_delivery.py"))
        self.assertLess(calls.index("decision_delivery.py"), calls.index("review_gate.py"))

    def test_guard_denial_still_wins_over_delivery(self):
        self.decision("acme-0001", "Keep widgets sorted.", paths=["**"])
        self.decision("acme-0006", "Mind the acme shell.", commands=["rm *", "acme-cli *"])
        for tool, tool_input in (
            ("apply_patch", self.patch(".env")),
            ("Bash", {"command": "rm -rf sandbox"}),
        ):
            with self.subTest(tool=tool):
                output = self.pre(tool, tool_input)
                self.assertTrue(adapter.denied(output))
                self.assertNotIn("Keep widgets sorted.", self.reason(output))
                self.assertNotIn("Mind the acme shell.", self.reason(output))
        # The guard's denial did not use up the delivery.
        self.assertIn("Keep widgets sorted.",
                      self.reason(self.pre("apply_patch", self.patch("src/a.py"))))
        self.assertIn("Mind the acme shell.",
                      self.reason(self.pre("Bash", {"command": "acme-cli sync"})))

    def test_delivery_failure_does_not_deny(self):
        self.decision("acme-0001", "Keep widgets sorted.", paths=["src/**"])
        # An unreadable state file makes delivery fail internally.
        (self.project / ".git/noemeo-decisions-delivered.json").mkdir()
        output = self.pre("apply_patch", self.patch("src/a.py"))
        self.assertFalse(adapter.denied(output))
        event = self.event("PreToolUse", "apply_patch", self.patch("src/a.py"))
        done = subprocess.run([sys.executable, str(ROOT / "codex/hook_adapter.py")],
            input=json.dumps(event), text=True, capture_output=True, check=True)
        self.assertFalse(adapter.denied(json.loads(done.stdout) if done.stdout.strip() else None))
        self.assertNotIn("could not verify policy", done.stdout)

    def test_post_patch_feedback_combines_ruff_and_decisions(self):
        self.install_fake_ruff()
        self.decision("acme-0004", "Prefer small widgets.", binding=False, paths=["src/**"])
        output = self.post("apply_patch", self.patch("src/a.py"))
        self.assertEqual(output["decision"], "block")
        self.assertIn("invented problem", output["reason"])
        self.assertIn("acme-0004", output["reason"])
        self.assertIn("Prefer small widgets.", output["reason"])
        # Decisions arrive once; ruff keeps reporting.
        again = self.post("apply_patch", self.patch("src/a.py"))
        self.assertIn("invented problem", again["reason"])
        self.assertNotIn("Prefer small widgets.", again["reason"])

    def test_post_feedback_for_every_edit_tool_without_ruff_findings(self):
        self.decision("acme-0004", "Prefer small widgets.", binding=False, paths=["docs/**"])
        (self.project / "docs/notes.md").write_text("notes\n")
        for n, tool in enumerate(("Write", "Edit", "MultiEdit", "apply_patch")):
            with self.subTest(tool=tool):
                target = {"command": self.patch("docs/notes.md")["command"]} if tool == "apply_patch" \
                    else {"file_path": str(self.project / "docs/notes.md")}
                output = self.post(tool, target, session=f"s{n}")
                self.assertEqual(output["decision"], "block")
                self.assertIn("Prefer small widgets.", output["reason"])
                self.assertIsNone(self.post(tool, target, session=f"s{n}"))

    def test_post_ruff_feedback_alone_is_unchanged(self):
        self.install_fake_ruff()
        output = self.post("Write", {"file_path": str(self.project / "src/a.py")})
        self.assertEqual(output["decision"], "block")
        self.assertIn("invented problem", output["reason"])

    def test_session_start_context_has_the_decisions_index(self):
        self.decision("acme-0001", "Keep widgets sorted.", paths=["src/**"])
        self.decision("acme-0005", "Always say hello.", binding=False, always="true")
        # session_context.sh runs `python3` from PATH, which may be too old.
        shim = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(shim)]))
        (shim / "python3").symlink_to(sys.executable)
        with patch.dict(os.environ, {"PATH": f"{shim}{os.pathsep}{os.environ['PATH']}"}):
            output = adapter.dispatch(self.event("SessionStart", "", {}))
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("## Decisions in this repo", context)
        self.assertIn("acme-0001: Summary of acme-0001", context)
        self.assertIn("Always say hello.", context)


def git_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


class CodexInstallTest(unittest.TestCase):
    def test_idempotent_and_live_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = git_repo(Path(tmp))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(installer.main([str(repo)]), 0)
            self.assertEqual(installer.compare(ROOT, repo)[1], {})
            self.assertEqual((repo / ".agents/skills/noemeo-ship").resolve(), ROOT / "skills/noemeo-ship")
            agents = list((repo / ".codex/agents").glob("*.toml"))
            self.assertEqual(len(agents), 7)
            for agent in agents:
                text = agent.read_text()
                parsed = tomllib.loads(text)
                self.assertEqual(parsed["name"], agent.stem)
                self.assertNotIn("\nmodel =", text)
                self.assertIn(str(ROOT / "agents" / (agent.stem + ".md")), text)

    def test_conflict_aborts_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = git_repo(Path(tmp))
            (repo / ".codex").mkdir()
            config = repo / ".codex/config.toml"
            config.write_text("# existing settings\n")
            with self.assertRaises(SystemExit):
                installer.main([str(repo)])
            self.assertFalse((repo / "AGENTS.md").exists())
            self.assertEqual(config.read_text(), "# existing settings\n")


if __name__ == "__main__":
    unittest.main()
