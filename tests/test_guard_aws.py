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


def denied(command: str, config: dict | None, env_profile: str | None = None) -> bool:
    with tempfile.TemporaryDirectory() as project:
        if config is not None:
            (Path(project) / ".claude").mkdir()
            (Path(project) / ".claude" / "noemeo-guard.json").write_text(json.dumps(config))
        env = {k: v for k, v in os.environ.items() if k != "AWS_PROFILE"}
        env["CLAUDE_PROJECT_DIR"] = project
        if env_profile:
            env["AWS_PROFILE"] = env_profile
        out = subprocess.run(
            [sys.executable, str(GUARD)],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
            capture_output=True,
            text=True,
            env=env,
            check=True,
        ).stdout
    return bool(out) and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


OPTED_IN = {"aws_profiles": ["acme-dev", "acme-admin"]}


class AwsProfileRule(unittest.TestCase):
    def test_without_a_profile_it_is_denied(self):
        self.assertTrue(denied("aws sts get-caller-identity", OPTED_IN))
        self.assertTrue(denied("cd infra && terraform plan", OPTED_IN))
        self.assertTrue(denied("aws s3 ls --profile personal", OPTED_IN))

    def test_a_listed_profile_is_allowed(self):
        self.assertFalse(denied("aws sts get-caller-identity --profile acme-dev", OPTED_IN))
        self.assertFalse(denied("aws s3 ls --profile=acme-admin", OPTED_IN))
        self.assertFalse(denied("AWS_PROFILE=acme-dev terraform plan", OPTED_IN))
        self.assertFalse(denied("terraform plan", OPTED_IN, env_profile="acme-dev"))

    def test_offline_commands_need_no_profile(self):
        for command in (
            "aws --version",
            "terraform fmt -check",
            "terraform -chdir=infra validate",
            "terraform init -backend=false",
        ):
            self.assertFalse(denied(command, OPTED_IN), command)

    def test_repos_that_dont_opt_in_are_unaffected(self):
        self.assertFalse(denied("aws sts get-caller-identity", None))
        self.assertFalse(denied("aws sts get-caller-identity", {"secrets": [".tokens"]}))


if __name__ == "__main__":
    unittest.main()
