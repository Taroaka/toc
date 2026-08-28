from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (REPO_ROOT / "toc", REPO_ROOT / "server", REPO_ROOT / "scripts")
DIRECT_STATE_MUTATION = re.compile(
    r"\b(?:state_path|state_file)\.(?:write_text|write_bytes|unlink|open)\s*\("
)
LEGACY_APPEND_CALL = re.compile(
    r"append_run_file_text\s*\([^)]*['\"]state\.txt['\"]",
    flags=re.DOTALL,
)


class StateWriterGuardTests(unittest.TestCase):
    def test_production_code_has_no_direct_canonical_state_writer(self) -> None:
        violations: list[str] = []
        for root in SOURCE_ROOTS:
            for path in root.rglob("*.py"):
                if path.name in {"state_store.py", "run_root_binding.py"}:
                    continue
                text = path.read_text(encoding="utf-8")
                if DIRECT_STATE_MUTATION.search(text) or LEGACY_APPEND_CALL.search(text):
                    violations.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(
            violations,
            [],
            "canonical state.txt must be mutated only through toc.state_store",
        )


if __name__ == "__main__":
    unittest.main()
