import base64
import importlib.util
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from toc.providers.kling import KlingClient, KlingConfig


def _tiny_png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class TestKlingProvider(unittest.TestCase):
    def test_standalone_kling_cli_blocks_unreviewed_provider_submission(self) -> None:
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate-kling-video.py"
        spec = importlib.util.spec_from_file_location(
            "generate_kling_video_under_test",
            script_path,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    str(script_path),
                    "--prompt",
                    "unreviewed raw prompt",
                    "--out",
                    "clip.mp4",
                ],
            ),
            mock.patch.object(module, "load_env_files"),
            mock.patch.object(module.KlingClient, "start_video_generation") as submit,
            self.assertRaisesRegex(SystemExit, "approved manifest request path"),
        ):
            module.main()

        submit.assert_not_called()

    def test_download_to_file_does_not_forward_provider_authorization(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self):  # noqa: ANN204
                return self

            def __exit__(self, *_args):  # noqa: ANN002, ANN204
                return False

            def read(self, limit: int = -1) -> bytes:
                body = b"video-bytes"
                return body if limit < 0 else body[:limit]

        class FakeOpener:
            def open(self, request, *, timeout):  # noqa: ANN001, ANN201
                captured["request"] = request
                captured["timeout"] = timeout
                return FakeResponse()

        public_dns = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        with tempfile.TemporaryDirectory(prefix="kling_download_") as td:
            out_path = Path(td) / "clip.mp4"
            with (
                mock.patch(
                    "toc.providers.media_download.socket.getaddrinfo",
                    return_value=public_dns,
                ),
                mock.patch(
                    "toc.providers.media_download.urllib.request.build_opener",
                    return_value=FakeOpener(),
                ),
            ):
                KlingClient(KlingConfig(api_key="provider-secret")).download_to_file(
                    uri="https://signed-cdn.example/clip.mp4?signature=abc",
                    out_path=out_path,
                )

            self.assertEqual(out_path.read_bytes(), b"video-bytes")

        request = captured["request"]
        self.assertEqual(request.full_url, "https://signed-cdn.example/clip.mp4?signature=abc")
        self.assertNotIn("authorization", {key.lower() for key in request.headers})

    def test_headers_support_official_jwt_auth(self) -> None:
        import json

        def b64url_decode(part: str) -> bytes:
            padded = part + "=" * ((4 - (len(part) % 4)) % 4)
            return base64.urlsafe_b64decode(padded.encode("ascii"))

        with mock.patch("toc.providers.kling.time.time", return_value=1_700_000_000):
            client = KlingClient(
                KlingConfig(
                    access_key="ak_test",
                    secret_key="sk_test",
                    api_key_header="authorization",
                    api_key_prefix="Bearer ",
                    jwt_expiration_seconds=1800,
                    jwt_clock_skew_seconds=5,
                )
            )
            headers = client._headers()

        auth = headers["authorization"]
        self.assertTrue(auth.startswith("Bearer "))
        token = auth.split(" ", 1)[1].strip()
        parts = token.split(".")
        self.assertEqual(len(parts), 3)

        payload = json.loads(b64url_decode(parts[1]).decode("utf-8"))
        self.assertEqual(payload["iss"], "ak_test")
        self.assertEqual(payload["exp"], 1_700_000_000 + 1800)
        self.assertEqual(payload["nbf"], 1_700_000_000 - 5)

    def test_build_video_payload_includes_frames_and_negative_prompt(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_") as td:
            tmp_path = Path(td)
            first = tmp_path / "first.png"
            last = tmp_path / "last.png"
            first.write_bytes(_tiny_png_bytes())
            last.write_bytes(_tiny_png_bytes())

            client = KlingClient(KlingConfig(api_key="test", video_model="kling-3.0"))
            payload = client.build_video_payload(
                prompt="p",
                duration_seconds=8,
                aspect_ratio="16:9",
                resolution="720p",
                input_image=first,
                last_frame_image=last,
                negative_prompt="nope",
            )

        self.assertEqual(payload["model"], "kling-3.0")
        self.assertEqual(payload["prompt"], "p")
        self.assertEqual(payload["duration_seconds"], 8)
        self.assertEqual(payload["aspect_ratio"], "16:9")
        self.assertEqual(payload["resolution"], "720p")
        self.assertEqual(payload["negative_prompt"], "nope")

        self.assertIn("first_frame_image", payload)
        self.assertIn("last_frame_image", payload)
        self.assertEqual(payload["first_frame_image"]["mime_type"], "image/png")
        self.assertEqual(payload["last_frame_image"]["mime_type"], "image/png")
        self.assertEqual(payload["first_frame_image"]["data"], base64.b64encode(_tiny_png_bytes()).decode("ascii"))
        self.assertEqual(payload["last_frame_image"]["data"], base64.b64encode(_tiny_png_bytes()).decode("ascii"))

    def test_build_video_payload_merges_extra_payload(self) -> None:
        client = KlingClient(KlingConfig(api_key="test", video_model="kling-3.0"))
        payload = client.build_video_payload(
            prompt="p",
            duration_seconds=6,
            aspect_ratio="9:16",
            resolution="720p",
            extra_payload={"foo": {"bar": 1}},
        )
        self.assertEqual(payload["foo"]["bar"], 1)
        self.assertEqual(payload["duration_seconds"], 6)

    def test_build_video_payload_rejects_protected_extra_payload_overrides(self) -> None:
        client = KlingClient(KlingConfig(api_key="test", video_model="kling-3.0"))
        for extra_payload in (
            {"prompt": "unreviewed"},
            {"duration_seconds": 12},
            {"input": {"prompt": "unreviewed"}},
        ):
            with self.subTest(extra_payload=extra_payload):
                with self.assertRaisesRegex(ValueError, "protected"):
                    client.build_video_payload(
                        prompt="reviewed",
                        duration_seconds=6,
                        aspect_ratio="9:16",
                        resolution="720p",
                        extra_payload=extra_payload,
                    )

    def test_start_video_generation_sends_extra_payload(self) -> None:
        captured = {}

        def fake_request_json(*, url, method, headers, json_payload, timeout_seconds):  # noqa: ANN001
            captured["payload"] = json_payload
            return {"id": "op_1"}

        with mock.patch("toc.providers.kling.request_json", side_effect=fake_request_json):
            client = KlingClient(KlingConfig(api_key="test", api_base="https://example.com", video_model="kling-3.0"))
            client.start_video_generation(
                prompt="p",
                duration_seconds=6,
                aspect_ratio="9:16",
                resolution="720p",
                extra_payload={"omni": {"mode": "on"}},
            )

        self.assertEqual(captured["payload"]["omni"]["mode"], "on")

    def test_extract_operation_id_status_and_video_uri(self) -> None:
        client = KlingClient(KlingConfig(api_key="test"))

        op_id = client.extract_operation_id({"data": {"id": "abc"}}, id_paths=["data.id"])
        self.assertEqual(op_id, "abc")

        status = client.extract_status({"data": {"status": "Succeeded"}}, status_paths=["data.status"])
        self.assertEqual(status, "succeeded")

        uri = client.extract_video_uri({"data": {"video": {"url": "https://cdn.example/video.mp4"}}}, video_url_paths=["data.video"])
        self.assertEqual(uri, "https://cdn.example/video.mp4")


if __name__ == "__main__":
    unittest.main()
