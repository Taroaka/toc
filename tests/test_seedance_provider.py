import socket
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from toc.providers.seedance import SeedanceClient, SeedanceConfig


class TestSeedanceProvider(unittest.TestCase):
    def test_public_media_download_rejects_response_over_byte_limit(self) -> None:
        from toc.providers.media_download import request_public_media_bytes

        class OversizedResponse:
            headers = {}

            def __enter__(self):  # noqa: ANN204
                return self

            def __exit__(self, *_args):  # noqa: ANN002, ANN204
                return False

            def read(self, limit: int = -1) -> bytes:
                return b"12345" if limit < 0 else b"12345"[:limit]

        class FakeOpener:
            def open(self, _request, *, timeout):  # noqa: ANN001, ANN201
                self.timeout = timeout
                return OversizedResponse()

        public_dns = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        with (
            mock.patch(
                "toc.providers.media_download.socket.getaddrinfo",
                return_value=public_dns,
            ),
            mock.patch(
                "toc.providers.media_download.urllib.request.build_opener",
                return_value=FakeOpener(),
            ),
            self.assertRaisesRegex(ValueError, "size limit"),
        ):
            request_public_media_bytes(
                url="https://signed-cdn.example/clip.mp4",
                timeout_seconds=10,
                max_bytes=4,
            )

    def test_download_to_file_does_not_forward_ark_authorization(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self):  # noqa: ANN204
                return self

            def __exit__(self, *_args):  # noqa: ANN002, ANN204
                return False

            def read(self, limit: int = -1) -> bytes:
                body = b"seedance-video"
                return body if limit < 0 else body[:limit]

        class FakeOpener:
            def open(self, request, *, timeout):  # noqa: ANN001, ANN201
                captured["request"] = request
                captured["timeout"] = timeout
                return FakeResponse()

        public_dns = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        with tempfile.TemporaryDirectory(prefix="seedance_download_") as td:
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
                SeedanceClient(SeedanceConfig(api_key="ark-secret")).download_to_file(
                    url="https://signed-cdn.example/clip.mp4?signature=xyz",
                    out_path=out_path,
                )

            self.assertEqual(out_path.read_bytes(), b"seedance-video")

        request = captured["request"]
        self.assertEqual(request.full_url, "https://signed-cdn.example/clip.mp4?signature=xyz")
        self.assertNotIn("authorization", {key.lower() for key in request.headers})

    def test_download_to_file_rejects_unsafe_media_urls_before_network_io(self) -> None:
        client = SeedanceClient(SeedanceConfig(api_key="ark-secret"))
        unsafe_urls = (
            "file:///etc/passwd",
            "https://user:password@cdn.example/clip.mp4",
            "http://127.0.0.1/clip.mp4",
            "http://[::1]/clip.mp4",
            "http://169.254.169.254/latest/meta-data/",
            "http://192.0.2.1/clip.mp4",
            "http://[64:ff9b::7f00:1]/clip.mp4",
            "http://[2002:7f00:1::]/clip.mp4",
        )

        with tempfile.TemporaryDirectory(prefix="seedance_unsafe_") as td:
            for index, url in enumerate(unsafe_urls):
                with self.subTest(url=url):
                    with (
                        mock.patch(
                            "toc.providers.media_download.urllib.request.build_opener"
                        ) as build_opener,
                        self.assertRaisesRegex(ValueError, "media URL"),
                    ):
                        client.download_to_file(
                            url=url,
                            out_path=Path(td) / f"clip-{index}.mp4",
                        )
                    build_opener.assert_not_called()

    def test_download_to_file_rejects_dns_resolving_to_private_address(self) -> None:
        private_dns = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))
        ]
        with tempfile.TemporaryDirectory(prefix="seedance_private_dns_") as td:
            with (
                mock.patch(
                    "toc.providers.media_download.socket.getaddrinfo",
                    return_value=private_dns,
                ),
                mock.patch(
                    "toc.providers.media_download.urllib.request.build_opener"
                ) as build_opener,
                self.assertRaisesRegex(ValueError, "non-public"),
            ):
                SeedanceClient(SeedanceConfig(api_key="ark-secret")).download_to_file(
                    url="https://private-dns.example/clip.mp4",
                    out_path=Path(td) / "clip.mp4",
                )
            build_opener.assert_not_called()

    def test_redirect_handler_validates_destination_and_strips_credentials(self) -> None:
        from toc.providers.media_download import _SafeMediaRedirectHandler

        public_dns = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        private_dns = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))
        ]
        handler = _SafeMediaRedirectHandler()
        initial = urllib.request.Request(
            "https://provider.example/task-output",
            method="GET",
            headers={
                "Authorization": "Bearer must-not-leak",
                "Proxy-Authorization": "proxy-secret",
                "Cookie": "session=secret",
                "Accept": "video/mp4",
            },
        )

        with mock.patch(
            "toc.providers.media_download.socket.getaddrinfo",
            return_value=public_dns,
        ):
            redirected = handler.redirect_request(
                initial,
                None,
                302,
                "Found",
                {},
                "https://signed-cdn.example/clip.mp4?signature=ok",
            )

        redirected_headers = {key.lower() for key in redirected.headers}
        self.assertNotIn("authorization", redirected_headers)
        self.assertNotIn("proxy-authorization", redirected_headers)
        self.assertNotIn("cookie", redirected_headers)
        self.assertEqual(redirected.get_header("Accept"), "video/mp4")

        with (
            mock.patch(
                "toc.providers.media_download.socket.getaddrinfo",
                return_value=private_dns,
            ),
            self.assertRaisesRegex(ValueError, "non-public"),
        ):
            handler.redirect_request(
                initial,
                None,
                302,
                "Found",
                {},
                "https://private-redirect.example/clip.mp4",
            )

    def test_frame_boundary_and_multimodal_reference_modes_are_mutually_exclusive(self) -> None:
        client = SeedanceClient(SeedanceConfig(api_key="test"))
        with tempfile.TemporaryDirectory(prefix="seedance_mode_") as td:
            image = Path(td) / "frame.png"
            reference = Path(td) / "reference.png"
            image.write_bytes(b"frame")
            reference.write_bytes(b"reference")

            with self.assertRaisesRegex(ValueError, "mutually exclusive"):
                client.build_video_payload(
                    model="seedance-1-0-lite-i2v-250428",
                    prompt="reviewed prompt",
                    duration_seconds=6,
                    ratio="9:16",
                    input_image=image,
                    reference_images=[reference],
                )

            payload = client.build_video_payload(
                model="seedance-1-0-lite-i2v-250428",
                prompt="reviewed prompt",
                duration_seconds=6,
                ratio="9:16",
                reference_images=[image, reference],
            )

        self.assertEqual(
            [item.get("role") for item in payload["content"][1:]],
            ["reference_image", "reference_image"],
        )

    def test_extra_payload_keeps_unprotected_provider_options(self) -> None:
        client = SeedanceClient(SeedanceConfig(api_key="test"))
        payload = client.build_video_payload(
            model="seedance-1-0-lite-i2v-250428",
            prompt="reviewed prompt",
            duration_seconds=6,
            ratio="9:16",
            extra_payload={"camera_fixed": True},
        )

        self.assertIs(payload["camera_fixed"], True)
        self.assertEqual(payload["content"][0]["text"], "reviewed prompt")

    def test_extra_payload_rejects_protected_request_overrides(self) -> None:
        client = SeedanceClient(SeedanceConfig(api_key="test"))
        for extra_payload in (
            {"content": [{"type": "text", "text": "unreviewed"}]},
            {"duration": 12},
            {"model": "other-model"},
            {"watermark": True},
            {"generate_audio": True},
        ):
            with self.subTest(extra_payload=extra_payload):
                with self.assertRaisesRegex(ValueError, "protected"):
                    client.build_video_payload(
                        model="seedance-1-0-lite-i2v-250428",
                        prompt="reviewed prompt",
                        duration_seconds=6,
                        ratio="9:16",
                        extra_payload=extra_payload,
                    )

    def test_seedance_1_0_provider_rejects_out_of_capability_requests(self) -> None:
        client = SeedanceClient(SeedanceConfig(api_key="test"))
        with tempfile.TemporaryDirectory(prefix="seedance_caps_") as td:
            references: list[Path] = []
            for index in range(5):
                reference = Path(td) / f"reference_{index}.png"
                reference.write_bytes(f"reference-{index}".encode("utf-8"))
                references.append(reference)

            with self.assertRaisesRegex(ValueError, "duration"):
                client.build_video_payload(
                    model="seedance-1-0-lite-i2v-250428",
                    prompt="reviewed prompt",
                    duration_seconds=13,
                    ratio="9:16",
                    reference_images=references[:2],
                )

            with self.assertRaisesRegex(ValueError, "reference image count"):
                client.build_video_payload(
                    model="seedance-1-0-lite-i2v-250428",
                    prompt="reviewed prompt",
                    duration_seconds=6,
                    ratio="9:16",
                    reference_images=references,
                )

            with self.assertRaisesRegex(ValueError, "no reviewed capability contract"):
                client.build_video_payload(
                    model="seedance-2-experimental",
                    prompt="reviewed prompt",
                    duration_seconds=6,
                    ratio="9:16",
                    reference_images=references[:2],
                )


if __name__ == "__main__":
    unittest.main()
