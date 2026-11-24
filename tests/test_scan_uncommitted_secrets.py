"""skills/noemeo-security-review/scripts/scan_uncommitted_secrets.py: what it
scans, what it skips, and that output never shows a token.

Run: python3 -m unittest discover tests

Runs the script as a subprocess in throwaway git repos in a
TemporaryDirectory; HOME and git config are isolated. Tests that need the
real gitleaks skip when it isn't on PATH. Fake tokens are assembled at
runtime from pieces, and secret-file names (dotenv, pem) are built in
Python so no source line names one literally.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "skills" / "noemeo-security-review" / "scripts" / "scan_uncommitted_secrets.py"
)
ENV_FILE = "." + "env"
PEM_FILE = "server." + "pem"
CERTS_DIR = "." + "certs"
HAVE_GITLEAKS = shutil.which("gitleaks") is not None

# 36-char bodies; the script's output must contain no part of them.
BODY_A = "aB3dE5gH7j" + "K9mN1pQ3sT" + "5vX7zA9cD1" + "fG3hJ5"
BODY_B = "Zy8xW6vU4t" + "S2rQ0pO8nM" + "6lK4jI2hG0" + "fE8dC6"
TOKEN_A = "ghp_" + BODY_A
TOKEN_B = "ghp_" + BODY_B


def leaky(token: str) -> str:
    return f"x = 1\nGITHUB_TOKEN = \"{token}\"\n"


class ScanScript(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.env = {
            k: v for k, v in os.environ.items()
            if not k.startswith(("GIT_", "CLAUDE_"))
        }
        self.env.update(
            HOME=str(self.tmp),
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_CONFIG_SYSTEM="/dev/null",
            GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
        )
        self.git("init", "-q", "-b", "main")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True,
                       capture_output=True)

    def write(self, name: str, content: str | bytes) -> Path:
        p = self.repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content)
        return p

    def commit(self, **files: str) -> None:
        for name, content in files.items():
            self.write(name, content)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")

    def scan(self, env=None, cwd=None):
        r = subprocess.run([sys.executable, str(SCRIPT)], cwd=cwd or self.repo,
                           env=env or self.env, capture_output=True, text=True)
        return r, r.stdout + r.stderr

    def assertNoToken(self, out: str, *bodies: str) -> None:
        for body in bodies:
            for piece in (body, body[:8], body[-8:], body[4:14]):
                self.assertNotIn(piece, out)

    def fake_gitleaks(self) -> tuple[Path, Path]:
        """A gitleaks wrapper on PATH that logs its arguments, then runs the real one."""
        real = shutil.which("gitleaks")
        bindir = self.tmp / "bin"
        bindir.mkdir()
        log = self.tmp / "gitleaks.log"
        wrapper = bindir / "gitleaks"
        wrapper.write_text(f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{log}"\nexec "{real}" "$@"\n')
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        return bindir, log

    # --- findings ---

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_modified_tracked_and_untracked_secrets_reported_redacted(self):
        self.commit(**{"tracked.py": "x = 1\n"})
        self.write("tracked.py", "x = 1\ny = 2\n" + leaky(TOKEN_A))  # secret on line 4
        self.write("new.py", "a = 1\nb = 2\n" + leaky(TOKEN_B))  # secret on line 4
        r, out = self.scan()
        self.assertEqual(r.returncode, 1, out)
        self.assertRegex(out, r"File:\s+tracked\.py\nLine:\s+4\n")
        self.assertRegex(out, r"File:\s+new\.py\nLine:\s+4\n")
        self.assertIn("files with leaks: 2", out)
        self.assertNoToken(out, BODY_A, BODY_B)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_clean_repo_exits_zero(self):
        self.commit(**{"a.py": "x = 1\n"})
        self.write("b.py", "y = 2\n")
        r, out = self.scan()
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("files with leaks: 0", out)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_repo_without_commits_scans_untracked_files(self):
        self.write("new.py", leaky(TOKEN_A))
        r, out = self.scan()
        self.assertEqual(r.returncode, 1, out)
        self.assertRegex(out, r"File:\s+new\.py\nLine:\s+2\n")
        self.assertNoToken(out, BODY_A)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_scanning_from_a_subdirectory_finds_repo_wide_changes(self):
        self.write("top.py", leaky(TOKEN_A))
        (self.repo / "sub").mkdir()
        r, out = self.scan(cwd=self.repo / "sub")
        self.assertEqual(r.returncode, 1, out)
        self.assertRegex(out, r"File:\s+top\.py")

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_one_files_token_never_appears_as_context_of_another(self):
        # Regression: a combined stream showed a neighbour's token tail unredacted.
        self.write("one.py", leaky(TOKEN_A))
        self.write("two.py", leaky(TOKEN_B))
        r, out = self.scan()
        self.assertEqual(r.returncode, 1, out)
        self.assertIn("files with leaks: 2", out)
        self.assertNoToken(out, BODY_A, BODY_B)

    # --- skips ---

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_guard_secret_files_skipped_and_never_passed_to_gitleaks(self):
        bindir, log = self.fake_gitleaks()
        self.write(ENV_FILE, leaky(TOKEN_A))
        self.write(PEM_FILE, leaky(TOKEN_A))
        self.write(f"{CERTS_DIR}/ca.crt", leaky(TOKEN_A))
        self.write("ok.py", "x = 1\n")
        env = dict(self.env, PATH=f"{bindir}{os.pathsep}{self.env['PATH']}")
        r, out = self.scan(env=env)
        self.assertEqual(r.returncode, 0, out)
        self.assertIn(f"skipped: {ENV_FILE} (secret file)", out)
        self.assertIn(f"skipped: {PEM_FILE} (secret file)", out)
        self.assertIn(f"skipped: {CERTS_DIR}/ca.crt (secret file)", out)
        calls = log.read_text()
        self.assertIn("ok.py", calls)
        for name in (ENV_FILE, PEM_FILE, "ca.crt"):
            self.assertNotIn(name, calls)
        self.assertNoToken(out, BODY_A)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_names_in_repo_guard_config_are_skipped_and_not_scanned(self):
        bindir, log = self.fake_gitleaks()
        self.write(".claude/noemeo-guard.json",
                   '{"secrets": ["vault.txt", "*.key"]}')
        self.write("vault.txt", leaky(TOKEN_A))
        self.write("my.key", leaky(TOKEN_A))
        env = dict(self.env, PATH=f"{bindir}{os.pathsep}{self.env['PATH']}")
        r, out = self.scan(env=env)
        self.assertIn("skipped: vault.txt (secret file)", out)
        self.assertIn("skipped: my.key (secret file)", out)
        calls = log.read_text()
        self.assertNotIn("vault.txt", calls)
        self.assertNotIn("my.key", calls)
        self.assertNoToken(out, BODY_A)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_binary_and_oversized_files_skipped_by_name(self):
        self.write("blob.bin", b"\x00\x01" + leaky(TOKEN_A).encode())
        big = self.repo / "big.txt"
        with big.open("wb") as f:
            f.write(leaky(TOKEN_B).encode())
            f.write(b"a" * (5 * 1024 * 1024 + 1))
        r, out = self.scan()
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("skipped: blob.bin (binary)", out)
        self.assertIn("skipped: big.txt (over 5 MB)", out)
        self.assertNoToken(out, BODY_A, BODY_B)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_deleted_tracked_file_not_scanned(self):
        bindir, log = self.fake_gitleaks()
        self.commit(**{"gone.py": leaky(TOKEN_A), "stay.py": "x = 1\n"})
        (self.repo / "gone.py").unlink()
        self.write("stay.py", "x = 2\n")
        env = dict(self.env, PATH=f"{bindir}{os.pathsep}{self.env['PATH']}")
        r, out = self.scan(env=env)
        self.assertEqual(r.returncode, 0, out)
        calls = log.read_text()
        self.assertNotIn("gone.py", calls)
        self.assertIn("stay.py", calls)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_gitignored_file_not_scanned(self):
        bindir, log = self.fake_gitleaks()
        self.write(".gitignore", "ignored.py\n")
        self.write("ignored.py", leaky(TOKEN_A))
        env = dict(self.env, PATH=f"{bindir}{os.pathsep}{self.env['PATH']}")
        r, out = self.scan(env=env)
        self.assertEqual(r.returncode, 0, out)
        self.assertNotIn("ignored.py", log.read_text())

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_renamed_and_edited_file_with_secret_is_reported(self):
        body = "".join(f"line {i} of ordinary text\n" for i in range(60))
        self.commit(**{"old.py": body})
        self.git("mv", "old.py", "moved.py")
        self.write("moved.py", body + leaky(TOKEN_A))
        self.git("add", "-A")
        r, out = self.scan()
        self.assertEqual(r.returncode, 1, out)
        self.assertRegex(out, r"File:\s+moved\.py\nLine:\s+62\n")
        self.assertNoToken(out, BODY_A)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_untracked_symlink_skipped_and_target_never_read(self):
        bindir, log = self.fake_gitleaks()
        outside = self.tmp / "outside.txt"
        outside.write_text(leaky(TOKEN_A))
        (self.repo / "link.txt").symlink_to(outside)
        env = dict(self.env, PATH=f"{bindir}{os.pathsep}{self.env['PATH']}")
        r, out = self.scan(env=env)
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("skipped: link.txt (symlink)", out)
        self.assertFalse(log.exists() and log.read_text().strip(), "gitleaks was called")
        self.assertNoToken(out, BODY_A)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_non_utf8_filename_does_not_crash(self):
        raw = os.fsencode(self.repo) + b"/caf\xe9.txt"
        try:
            with open(raw, "w") as f:
                f.write("x = 1\n")
        except OSError:
            self.skipTest("filesystem refuses non-UTF-8 file names")
        r, out = self.scan()
        self.assertNotIn("Traceback", out)
        self.assertEqual(r.returncode, 0, out)

    def test_git_helper_decodes_non_utf8_names_without_crashing(self):
        # Platform-independent twin of the file-system test above (macOS
        # refuses to create such a name): feed the helper git's raw bytes.
        import importlib.util
        from unittest import mock

        spec = importlib.util.spec_from_file_location("scan_under_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fake = subprocess.CompletedProcess([], 0, stdout=b"caf\xe9.txt\0ok.py\0")
        with mock.patch.object(mod.subprocess, "run", return_value=fake):
            names = mod.git("ls-files")
        self.assertEqual(len(names), 2)
        self.assertEqual(names[1], "ok.py")
        self.assertEqual(os.fsencode(names[0]), b"caf\xe9.txt")

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks not installed")
    def test_gitleaks_failure_is_reported_not_counted_as_leak(self):
        bindir = self.tmp / "failbin"
        bindir.mkdir()
        wrapper = bindir / "gitleaks"
        wrapper.write_text("#!/bin/sh\necho boom >&2\nexit 3\n")
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        self.write("a.py", "x = 1\n")
        env = dict(self.env, PATH=f"{bindir}{os.pathsep}{self.env['PATH']}")
        r, out = self.scan(env=env)
        self.assertIn("a.py: gitleaks failed: boom", out)
        self.assertIn("files with leaks: 0", out)

    # --- environment ---

    def test_missing_gitleaks_exits_two_with_message(self):
        # PATH holds only a git symlink, so gitleaks can't be found.
        bindir = self.tmp / "gitonly"
        bindir.mkdir()
        (bindir / "git").symlink_to(shutil.which("git"))
        env = dict(self.env, PATH=str(bindir))
        r, out = self.scan(env=env)
        self.assertEqual(r.returncode, 2, out)
        self.assertIn("gitleaks not installed", out)


if __name__ == "__main__":
    unittest.main()
