import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
CODEX_ALIAS = ROOT / "codex_skills"
CLAUDE_SKILLS_DIR = ROOT / ".claude" / "skills"


class TestSharedSkills(unittest.TestCase):
    def test_codex_alias_points_to_skills(self) -> None:
        self.assertTrue(CODEX_ALIAS.is_symlink())
        self.assertEqual(os.readlink(CODEX_ALIAS), "skills")

    def test_shared_skill_frontmatter_names_match_directory(self) -> None:
        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
                continue

            skill_md = skill_dir / "SKILL.md"
            self.assertTrue(skill_md.exists(), f"Missing SKILL.md: {skill_dir}")

            lines = skill_md.read_text(encoding="utf-8").splitlines()
            self.assertGreaterEqual(len(lines), 4, f"Unexpected short SKILL.md: {skill_md}")
            self.assertEqual(lines[0], "---", f"Missing frontmatter start: {skill_md}")
            self.assertIn("---", lines[1:], f"Missing frontmatter end: {skill_md}")
            self.assertEqual(lines[1], f"name: {skill_dir.name}", f"name mismatch: {skill_md}")
            text = "\n".join(lines)
            self.assertIn("Use when:", text, f"Missing Use when in description: {skill_md}")
            self.assertNotIn("Accepts args:", text, f"Shared skills should not declare Accepts args: {skill_md}")

    def test_claude_skill_symlinks_point_to_shared_source(self) -> None:
        expected_skills = {
            "ai-idea-studio",
            "era-explainer",
            "folktale-researcher",
            "improve-workflow",
            "neta-collector",
            "selfhelp-trend-researcher",
            "skill-smoke-test",
            "vertical-shorts-creator",
        }
        for skill_name in expected_skills:
            skill_path = CLAUDE_SKILLS_DIR / skill_name
            self.assertTrue(skill_path.is_symlink(), f"Expected symlink: {skill_path}")
            self.assertEqual(os.readlink(skill_path), f"../../skills/{skill_name}")
            self.assertTrue(skill_path.resolve().samefile(SKILLS_DIR / skill_name))

    def test_install_script_copies_shared_skills_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            env = os.environ.copy()
            env["CODEX_HOME"] = str(codex_home)

            subprocess.run(
                ["bash", "scripts/ai/install-codex-skills.sh"],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            installed_dir = codex_home / "skills"
            self.assertTrue(installed_dir.exists())

            installed_names = sorted(
                path.name for path in installed_dir.iterdir() if path.is_dir()
            )
            source_names = sorted(
                path.name
                for path in SKILLS_DIR.iterdir()
                if path.is_dir() and not path.name.startswith("_") and (path / "SKILL.md").exists()
            )

            self.assertEqual(installed_names, source_names)
            self.assertFalse((installed_dir / "_shared").exists())


if __name__ == "__main__":
    unittest.main()
