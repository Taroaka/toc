import base64
import unittest
from pathlib import Path
from unittest import mock
import tempfile

from toc.providers.gemini import GeminiClient, GeminiConfig


def _tiny_png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class TestGeminiProviderPayloads(unittest.TestCase):
    def test_generate_image_sends_reference_images(self) -> None:
        with self.subTest("payload contains inlineData parts"):
            with unittest.mock.patch("toc.providers.gemini.request_json") as m:
                captured = {}

                def fake_request_json(*, url, method, headers, json_payload, timeout_seconds):  # noqa: ANN001
                    captured["payload"] = json_payload
                    png_b64 = base64.b64encode(_tiny_png_bytes()).decode("ascii")
                    return {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"inlineData": {"mimeType": "image/png", "data": png_b64}},
                                    ]
                                }
                            }
                        ]
                    }

                m.side_effect = fake_request_json
                import tempfile

                with tempfile.TemporaryDirectory(prefix="toc_test_") as td:
                    tmp_path = Path(td)
                    ref1 = tmp_path / "ref1.png"
                    ref2 = tmp_path / "ref2.jpg"
                    ref1.write_bytes(_tiny_png_bytes())
                    ref2.write_bytes(b"\xff\xd8\xff" + b"\x00" * 32)

                    client = GeminiClient(GeminiConfig(api_key="test"))
                    image_bytes, mime, _ = client.generate_image(
                        prompt="p",
                        aspect_ratio="16:9",
                        image_size="2K",
                        reference_images=[ref1, ref2],
                    )

                self.assertTrue(image_bytes.startswith(b"\x89PNG"))
                self.assertEqual(mime, "image/png")

                parts = captured["payload"]["contents"][0]["parts"]
                self.assertEqual(parts[0]["text"], "p")
                self.assertTrue(any("inlineData" in p for p in parts[1:]))

    def test_generate_image_downscales_large_reference_images_before_upload(self) -> None:
        captured = {}

        def fake_request_json(*, url, method, headers, json_payload, timeout_seconds):  # noqa: ANN001
            captured["payload"] = json_payload
            png_b64 = base64.b64encode(_tiny_png_bytes()).decode("ascii")
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"inlineData": {"mimeType": "image/png", "data": png_b64}},
                            ]
                        }
                    }
                ]
            }

        with mock.patch("toc.providers.gemini.request_json", side_effect=fake_request_json):
            from PIL import Image

            with tempfile.TemporaryDirectory(prefix="toc_test_") as td:
                tmp_path = Path(td)
                ref = tmp_path / "large.png"
                Image.new("RGB", (4000, 2500), color=(80, 120, 160)).save(ref, format="PNG")
                raw_size = ref.stat().st_size

                client = GeminiClient(GeminiConfig(api_key="test"))
                client.generate_image(
                    prompt="p",
                    aspect_ratio="16:9",
                    image_size="2K",
                    reference_images=[ref],
                )

        parts = captured["payload"]["contents"][0]["parts"]
        encoded = parts[1]["inlineData"]["data"]
        payload_bytes = len(base64.b64decode(encoded))
        self.assertLess(payload_bytes, raw_size)
        self.assertIn(parts[1]["inlineData"]["mimeType"], {"image/jpeg", "image/png"})

    def test_start_video_generation_sends_last_frame(self) -> None:
        captured = {}

        def fake_request_json(*, url, method, headers, json_payload, timeout_seconds):  # noqa: ANN001
            captured["payload"] = json_payload
            return {"name": "operations/test"}

        with mock.patch("toc.providers.gemini.request_json", side_effect=fake_request_json):
            import tempfile

            with tempfile.TemporaryDirectory(prefix="toc_test_") as td:
                tmp_path = Path(td)
                first = tmp_path / "first.png"
                last = tmp_path / "last.png"
                first.write_bytes(_tiny_png_bytes())
                last.write_bytes(_tiny_png_bytes())

                client = GeminiClient(GeminiConfig(api_key="test"))
                client.start_video_generation(
                    prompt="p",
                    duration_seconds=8,
                    aspect_ratio="16:9",
                    resolution="720p",
                    input_image=first,
                    last_frame_image=last,
                )

        inst = captured["payload"]["instances"][0]
        self.assertIn("image", inst)
        self.assertIn("endImage", inst)

if __name__ == "__main__":
    unittest.main()
