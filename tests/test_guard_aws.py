"""The guard's opt-in AWS profile rule: in a repo that lists its AWS
profiles, an aws/terraform command that can reach AWS must use one.

Run: python3 -m unittest discover tests

Runs hooks/guard.py as Claude Code does (JSON on stdin) against a
throwaway project directory.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / "hooks" / "guard.py"
OPTED_IN = {"aws_profiles": ["acme-dev", "acme-admin"]}


def run_guard(
    command: str, config, env_profile: str | None = None
) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as project:
        if config is not None:
            (Path(project) / ".claude").mkdir()
            text = config if isinstance(config, str) else json.dumps(config)
            (Path(project) / ".claude" / "noemeo-guard.json").write_text(text)
        env = {k: v for k, v in os.environ.items() if k != "AWS_PROFILE"}
        env["CLAUDE_PROJECT_DIR"] = project
        if env_profile:
            env["AWS_PROFILE"] = env_profile
        return subprocess.run(
            [sys.executable, str(GUARD)],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
            capture_output=True,
            text=True,
            env=env,
        )


def denied(command: str, config=OPTED_IN, env_profile: str | None = None) -> bool:
    out = run_guard(command, config, env_profile)
    if out.returncode != 0:
        raise AssertionError(f"guard crashed: {out.stderr}")
    return (
        bool(out.stdout)
        and json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    )


# (command, AWS_PROFILE in the session, denied?)
CASES = [
    # no profile anywhere
    ("aws sts get-caller-identity", None, True),
    ("cd infra && terraform plan", None, True),
    ("terraform -chdir=infra plan", None, True),
    ("terraform init -backend-config=dev.hcl", None, True),
    ("aws s3 ls --profile personal", None, True),
    ("echo $(aws s3 ls)", None, True),
    ("/usr/local/bin/aws s3 ls", None, True),
    ("sudo aws s3 ls", None, True),
    ("sudo -E aws s3 ls", None, True),
    ("(aws s3 ls)", None, True),
    ("{ aws s3 ls; }", None, True),
    ("if true; then aws s3 ls; fi", None, True),
    ("for b in x; do aws s3 ls; done", None, True),
    ("timeout 5 aws s3 ls", None, True),
    ("if aws s3 ls; then echo; fi", None, True),
    ("while aws s3 ls; do sleep 1; done", None, True),
    ("terraform providers", None, True),
    ("terraform -chdir=x graph -type=plan", None, True),
    ("nohup aws s3 ls", None, True),
    ("echo x | xargs -n 1 aws s3 ls", None, True),
    ("env -i aws s3 ls", None, True),
    # a listed profile
    ("aws sts get-caller-identity --profile acme-dev", None, False),
    ("aws s3 ls --profile=acme-admin", None, False),
    ("AWS_PROFILE=acme-dev terraform plan", None, False),
    ("env AWS_PROFILE=acme-dev aws s3 ls", None, False),
    ("terraform plan", "acme-dev", False),
    ("aws s3 ls", "acme-dev", False),
    # terraform has no --profile flag
    ("terraform plan --profile acme-dev", None, True),
    # the command overrides the session's profile
    ("unset AWS_PROFILE && aws s3 ls", "acme-dev", True),
    ("export AWS_PROFILE=personal; aws s3 ls", "acme-dev", True),
    ("export AWS_PROFILE=personal && terraform plan", "acme-dev", True),
    ("env -u AWS_PROFILE aws s3 ls", "acme-dev", True),
    ("AWS_PROFILE= aws s3 ls", "acme-dev", True),
    ("AWS_PROFILE=personal aws s3 ls", "acme-dev", True),
    ("unset AWS_PROFILE && aws s3 ls --profile acme-dev", "acme-dev", False),
    # offline
    ("aws --version", None, False),
    ("aws s3 help", None, False),
    ("aws configure list", None, False),
    ("aws configure list-profiles", None, False),
    ("terraform", None, False),
    ("terraform fmt -check", None, False),
    ("terraform -chdir=infra validate", None, False),
    ("terraform init -backend=false", None, False),
    ("terraform providers lock", None, False),
]


class AwsProfileRule(unittest.TestCase):
    def test_cases(self):
        for command, env_profile, expected in CASES:
            with self.subTest(command=command, env=env_profile):
                self.assertEqual(denied(command, env_profile=env_profile), expected)

    def test_repos_that_dont_opt_in_are_unaffected(self):
        self.assertFalse(denied("aws sts get-caller-identity", None))
        self.assertFalse(
            denied("aws sts get-caller-identity", {"secrets": [".tokens"]})
        )

    def test_a_malformed_config_keeps_the_rest_of_the_guard_working(self):
        for config in ('{"aws_profiles": true}', '{"aws_profiles": 5}', '{"aws_profiles": "x"}',
                       "[]", "not json", ""):  # fmt: skip
            with self.subTest(config=config):
                self.assertTrue(denied("rm -rf build", config))
                self.assertFalse(denied("aws s3 ls --profile a", config))

    def test_the_other_rules_still_apply_in_an_opted_in_repo(self):
        self.assertTrue(denied("rm -rf build"))
        self.assertTrue(denied("git push --force"))
        self.assertTrue(denied("cat .env"))
        self.assertTrue(denied("timeout 5 rm -rf build"))
        self.assertFalse(denied("ls"))


if __name__ == "__main__":
    unittest.main()
