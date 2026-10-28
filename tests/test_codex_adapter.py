"""Codex boundary regressions; no cloud calls, paid APIs or developer data."""

import contextlib
import importlib.util
import io
import json
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
        with tempfile.TemporaryDirectory() as tmp:
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
