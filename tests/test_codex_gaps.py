"""Regression reproductions; all target data lives in temporary directories."""
import tempfile
from pathlib import Path
import subprocess
import unittest
from test_codex_adapter import adapter, installer, ROOT

class CodexGapTest(unittest.TestCase):
    def test_installer_parent_file_conflict_aborts_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q', tmp], check=True)
            sentinel = repo / '.codex'
            sentinel.write_text('existing local file\n')
            with self.assertRaises(SystemExit):
                installer.main([tmp])
            self.assertEqual(sentinel.read_text(), 'existing local file\n')
            self.assertFalse((repo / 'AGENTS.md').exists())
            self.assertFalse((repo / '.agents').exists())

    def test_raw_exec_target_repository_requires_its_own_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'target'
            repo.mkdir()
            def git(*args):
                subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
            git('init', '-b', 'main')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (repo / 'file.txt').write_text('baseline\n')
            git('add', 'file.txt')
            git('commit', '-m', 'baseline')
            git('update-ref', 'refs/remotes/origin/main', 'HEAD')
            (repo / 'file.txt').write_text('unreviewed\n')
            for workdir in (str(repo), 'target'):
                with self.subTest(workdir=workdir):
                    result = adapter.dispatch({'hook_event_name': 'PreToolUse', 'cwd': tmp,
                        'tool_name': 'exec_command', 'tool_input': {'workdir': workdir,
                        'cmd': 'gh pr create --base main --title fixture --body fixture'}})
                    self.assertTrue(adapter.denied(result))
