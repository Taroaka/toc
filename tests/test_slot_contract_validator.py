import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import shutil


class TestSlotContractValidator(unittest.TestCase):
    def test_slot_contract_validator(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/validate-slot-contract.py", "--root", str(Path(".").resolve())],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Slot contract valid.", result.stdout)

    def test_slot_contract_validator_rejects_stale_slot_reference(self) -> None:
        root = Path(".").resolve()
        with tempfile.TemporaryDirectory(prefix="toc_slot_contract_copy_") as td:
            temp_root = Path(td)
            for rel in (
                "scripts/validate-slot-contract.py",
                "toc/run_index.py",
                "docs/system-architecture.md",
                "docs/how-to-run.md",
                "docs/data-contracts.md",
                "docs/root-pointer-guide.md",
                "workflow/state-schema.txt",
            ):
                src = root / rel
                dst = temp_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

            how_to_run = temp_root / "docs/how-to-run.md"
            how_to_run.write_text(how_to_run.read_text(encoding="utf-8") + "\n- stale slot: `p999`\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(temp_root / "scripts/validate-slot-contract.py"), "--root", str(temp_root)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("contains unknown or stale slot codes: p999", result.stderr)


if __name__ == "__main__":
    unittest.main()
