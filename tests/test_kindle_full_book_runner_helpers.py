import importlib.util
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "kindle" / "run-kindle-full-book.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "kindle") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "kindle"))

spec = importlib.util.spec_from_file_location("kindle_full_book_runner", RUNNER_PATH)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)

image_dark_ratio = module.image_dark_ratio
is_intentionally_sparse_page = module.is_intentionally_sparse_page
prepare_vision_image = module.prepare_vision_image


class TestKindleFullBookRunnerHelpers(unittest.TestCase):
    def test_sparse_page_detection_distinguishes_light_and_dense_pages(self) -> None:
        fixture_dir = Path("/tmp/kindle-runner-helper-tests")
        fixture_dir.mkdir(parents=True, exist_ok=True)

        sparse_path = fixture_dir / "sparse.png"
        dense_path = fixture_dir / "dense.png"

        sparse = Image.new("L", (400, 400), 255)
        sparse_draw = ImageDraw.Draw(sparse)
        sparse_draw.text((340, 10), "題", fill=0)
        sparse.save(sparse_path)

        dense = Image.new("L", (400, 400), 255)
        dense_draw = ImageDraw.Draw(dense)
        for x in range(20, 380, 24):
            dense_draw.rectangle((x, 20, x + 8, 360), fill=0)
        dense.save(dense_path)

        sparse_ratio = image_dark_ratio(sparse_path)
        dense_ratio = image_dark_ratio(dense_path)

        self.assertIsNotNone(sparse_ratio)
        self.assertIsNotNone(dense_ratio)
        self.assertTrue(is_intentionally_sparse_page(sparse_ratio))
        self.assertFalse(is_intentionally_sparse_page(dense_ratio))
        self.assertLess(sparse_ratio, dense_ratio)

    def test_prepare_vision_image_adds_white_padding(self) -> None:
        fixture_dir = Path("/tmp/kindle-runner-helper-tests")
        fixture_dir.mkdir(parents=True, exist_ok=True)
        source_path = fixture_dir / "source.png"
        output_path = fixture_dir / "prepared.png"

        source = Image.new("RGB", (100, 200), (240, 240, 240))
        ImageDraw.Draw(source).rectangle((80, 20, 95, 180), fill=(0, 0, 0))
        source.save(source_path)

        prepare_vision_image(source_path, output_path)

        prepared = Image.open(output_path)
        self.assertGreater(prepared.size[0], 100)
        self.assertGreater(prepared.size[1], 200)
        self.assertEqual(prepared.getpixel((5, 5)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
