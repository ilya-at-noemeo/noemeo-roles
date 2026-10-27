"""Roles are loaded, not just documented, and every path to one resolves.

Run: python3 -m unittest discover tests

- Every role definition in roles/ is read by at least one skill or agent;
  a role nothing loads is documentation, and belongs in docs/ or nowhere.
- A skill names a role relative to its own base directory
  (`../../roles/...`); that path must exist.
- Agents, the README and docs/ name roles from the repo root
  (`roles/...`); that path must exist too.
- No role definition is left in the old top-level folders.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLES = ROOT / "roles"
# A role path as written in Markdown: optional ../ prefixes, then roles/<kind>/<file>.md
ROLE_PATH = re.compile(r"((?:\.\./)*)(roles/[a-z-]+/[a-z-]+\.md)")


def role_files() -> list[Path]:
    return sorted(ROLES.rglob("*.md"))


def skill_files() -> list[Path]:
    return sorted((ROOT / "skills").glob("*/SKILL.md"))


def agent_files() -> list[Path]:
    return sorted((ROOT / "agents").glob("*.md"))


def doc_files() -> list[Path]:
    return [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


class RolesTest(unittest.TestCase):
    def test_there_are_roles(self) -> None:
        self.assertTrue(role_files(), "no role definitions found in roles/")

    def test_every_role_is_loaded_by_a_skill_or_agent(self) -> None:
        readers = [*skill_files(), *agent_files()]
        loaded = {
            m.group(2) for f in readers for m in ROLE_PATH.finditer(f.read_text())
        }
        for role in role_files():
            rel = role.relative_to(ROOT).as_posix()
            with self.subTest(role=rel):
                self.assertIn(
                    rel,
                    loaded,
                    f"{rel} is read by no skill or agent: wire it into one, "
                    "or it's documentation, not a role",
                )

    def test_skill_role_paths_resolve_from_the_skill(self) -> None:
        for skill in skill_files():
            for m in ROLE_PATH.finditer(skill.read_text()):
                with self.subTest(skill=skill.parent.name, path=m.group(0)):
                    base = skill.parent if m.group(1) else ROOT
                    self.assertTrue(
                        (base / m.group(0)).resolve().is_file(),
                        f"{m.group(0)} doesn't resolve from {skill.parent.name}",
                    )

    def test_root_relative_role_paths_resolve(self) -> None:
        for f in [*agent_files(), *doc_files()]:
            for m in ROLE_PATH.finditer(f.read_text()):
                if m.group(1):
                    continue  # an agent quoting a skill-relative path
                with self.subTest(file=f.relative_to(ROOT).as_posix(), path=m.group(2)):
                    self.assertTrue((ROOT / m.group(2)).is_file(), f"{m.group(2)} doesn't exist")

    def test_no_roles_left_in_old_folders(self) -> None:
        for old in ("product", "engineering", "research"):
            with self.subTest(folder=old):
                self.assertFalse((ROOT / old).exists(), f"{old}/ should live under roles/")


if __name__ == "__main__":
    unittest.main()
