from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from toc.providers.higgsfield import HiggsfieldClient, HiggsfieldConfig


class TestHiggsfieldProvider(unittest.TestCase):
    def test_authenticated_api_redirect_is_refused_and_api_origin_is_fixed(self) -> None:
        from toc.providers.higgsfield import _NoRedirectHandler

        request = urllib.request.Request(
            "https://api.higgsfield.ai/files/generate-upload-url",
            headers={"Authorization": "Key id:secret"},
        )
        self.assertIsNone(_NoRedirectHandler().redirect_request(
            request, None, 307, "Temporary Redirect", {}, "https://attacker.example/collect",
        ))
        with self.assertRaisesRegex(ValueError, "api.higgsfield.ai"):
            HiggsfieldConfig(api_key="id:secret", api_base="https://attacker.example")

    def test_upload_rejects_credential_headers_from_presign_response(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "in.png"
            image.write_bytes(b"image")
            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            with (
                mock.patch.object(client, "_api_request_json", return_value={
                    "upload_url": "https://storage.example/upload",
                    "public_url": "https://cdn.example/in.png",
                    "upload_headers": {"Content-Type": "image/png", "Authorization": "Bearer injected"},
                }),
                mock.patch("toc.providers.higgsfield.validate_media_url", side_effect=lambda url: url),
                mock.patch("toc.providers.higgsfield.urllib.request.build_opener") as opener,
                self.assertRaisesRegex(RuntimeError, "upload failed"),
            ):
                client._upload_file(image)
            opener.assert_not_called()

    def test_image_to_video_omits_ratio_parameter_and_rejects_mismatched_frame(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "frame.png"
            Image.new("RGB", (160, 90)).save(image)
            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            with mock.patch.object(client, "_upload_file", return_value="https://cdn.example/frame.png"):
                payload = client._build_payload(
                    model="bytedance/seedance-2.5/image-to-video", prompt="move",
                    duration_seconds=5, aspect_ratio="16:9", resolution="720p",
                    input_image=image, last_frame_image=None, reference_images=None, generate_audio=False,
                )
                self.assertNotIn("aspect_ratio", payload)
                with self.assertRaisesRegex(ValueError, "inherits the first frame"):
                    client._build_payload(
                        model="bytedance/seedance-2.5/image-to-video", prompt="move",
                        duration_seconds=5, aspect_ratio="4:3", resolution="720p",
                        input_image=image, last_frame_image=None, reference_images=None, generate_audio=False,
                    )

    def test_presigned_upload_never_receives_api_authorization(self) -> None:
        captured: dict[str, object] = {}

        class Response:
            def __enter__(self):  # noqa: ANN204
                return self

            def __exit__(self, *_args):  # noqa: ANN002, ANN204
                return False

            def read(self, _size: int = -1) -> bytes:
                return b""

        def open_url(request, *, timeout):  # noqa: ANN001, ANN201
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

        class FakeOpener:
            def open(self, request, *, timeout):  # noqa: ANN001, ANN201
                return open_url(request, timeout=timeout)

        def build_opener(*handlers):  # noqa: ANN002, ANN201
            captured["handlers"] = handlers
            return FakeOpener()

        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "in.png"
            image.write_bytes(b"image")
            client = HiggsfieldClient(HiggsfieldConfig(api_key="key-id:secret"))
            with (
                mock.patch.object(client, "_api_request_json", return_value={
                    "upload_url": "https://storage.example/upload?token=private",
                    "public_url": "https://cdn.example/input.png",
                    "upload_headers": {"Content-Type": "image/png", "x-amz-tagging": "retention=temporary"},
                }) as request_json,
                mock.patch("toc.providers.higgsfield.validate_media_url", side_effect=lambda url: url),
                mock.patch("toc.providers.higgsfield.urllib.request.build_opener", side_effect=build_opener),
            ):
                result = client._upload_file(image)

        self.assertEqual(result, "https://cdn.example/input.png")
        request_json.assert_called_once()
        upload_request = captured["request"]
        header_names = {name.lower() for name in upload_request.headers}
        self.assertNotIn("authorization", header_names)
        self.assertIn("x-amz-tagging", header_names)
        from toc.providers.media_download import _SafeMediaRedirectHandler
        self.assertTrue(any(isinstance(handler, _SafeMediaRedirectHandler) for handler in captured["handlers"]))

    def test_image_mode_preserves_all_fields_and_upload_does_not_forward_auth(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image = root / "frame.png"
            end = root / "end.png"
            image.write_bytes(b"first")
            end.write_bytes(b"last")
            uploaded: list[object] = []
            submitted: list[object] = []
            statuses = iter([
                {"status": "queued", "request_id": "req-1", "status_url": "https://api.higgsfield.ai/requests/req-1/status"},
                {"status": "completed", "request_id": "req-1", "video": {"url": "https://cdn.example/video.mp4"}},
            ])

            def upload(path: Path) -> str:
                uploaded.append(path)
                return f"https://cdn.example/{path.name}"

            def request_json(**kwargs):  # noqa: ANN003, ANN201
                if kwargs["method"] == "POST" and "/files/" not in kwargs["url"]:
                    submitted.append(kwargs)
                    return next(statuses)
                if kwargs["method"] == "GET":
                    return next(statuses)
                raise AssertionError(kwargs)

            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            with (
                mock.patch.object(client, "_api_request_json", side_effect=request_json),
                mock.patch.object(client, "_upload_file", side_effect=upload),
                mock.patch.object(client, "_image_ratio_matches", return_value=True),
                mock.patch("toc.providers.higgsfield.validate_media_url", side_effect=lambda url: url),
                mock.patch("toc.providers.higgsfield.request_public_media_bytes", return_value=b"video-bytes"),
            ):
                result = client.generate_video(
                    model="bytedance/seedance-2.5/image-to-video",
                    prompt="move gently",
                    duration_seconds=8,
                    aspect_ratio="9:16",
                    resolution="1080p",
                    input_image=image,
                    last_frame_image=end,
                    reference_images=[],
                    generate_audio=True,
                    out_path=root / "clip.mp4",
                    journal_path=root / "journal.json",
                    request_digest="sha256:request",
                    poll_every_seconds=0,
                )

            self.assertEqual(len(uploaded), 2)
            self.assertEqual(submitted[0]["json_payload"], {
                "prompt": "move gently", "duration": 8,
                "resolution": "1080p", "image_url": "https://cdn.example/frame.png",
                "end_image_url": "https://cdn.example/end.png", "generate_audio": True,
            })
            self.assertEqual(result["status"], "completed")
            self.assertEqual((root / "clip.mp4").read_bytes(), b"video-bytes")

    def test_reference_mode_keeps_order_and_rejects_unknown_combinations(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            images = [root / "a.png", root / "b.png"]
            for path in images:
                path.write_bytes(b"image")
            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            with (
                mock.patch.object(client, "_upload_file", side_effect=["https://cdn.example/a", "https://cdn.example/b"]),
                mock.patch.object(client, "_api_request_json", return_value={"status": "queued", "request_id": "req-2", "status_url": "https://api.higgsfield.ai/requests/req-2/status"}) as request,
            ):
                with self.assertRaisesRegex(ValueError, "cannot combine"):
                    client.generate_video(model="bytedance/seedance-2.5/reference-to-video", prompt="p", duration_seconds=5, aspect_ratio="16:9", resolution="720p", input_image=images[0], last_frame_image=None, reference_images=images, generate_audio=False, out_path=root / "out.mp4", journal_path=root / "j.json", request_digest="d", poll=False)
            with (
                mock.patch.object(client, "_upload_file", side_effect=["https://cdn.example/a", "https://cdn.example/b"]),
                mock.patch.object(client, "_api_request_json", return_value={"status": "queued", "request_id": "req-2", "status_url": "https://api.higgsfield.ai/requests/req-2/status"}) as request,
            ):
                client.generate_video(model="bytedance/seedance-2.5/reference-to-video", prompt="p", duration_seconds=5, aspect_ratio="16:9", resolution="720p", input_image=None, last_frame_image=None, reference_images=images, generate_audio=False, out_path=root / "out.mp4", journal_path=root / "j.json", request_digest="d", poll=False)
            payload = request.call_args.kwargs["json_payload"]
            self.assertEqual(payload["image_urls"], ["https://cdn.example/a", "https://cdn.example/b"])
            self.assertEqual(payload["generate_audio"], False)

    def test_uncertain_submit_is_not_retried_and_saved_request_can_resume(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / "ref.png"
            ref.write_bytes(b"ref")
            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            kwargs = dict(model="bytedance/seedance-2.5/reference-to-video", prompt="p", duration_seconds=5, aspect_ratio="16:9", resolution="720p", input_image=None, last_frame_image=None, reference_images=[ref], generate_audio=False, out_path=root / "out.mp4", journal_path=root / "j.json", request_digest="digest", poll=False)
            with mock.patch.object(client, "_upload_file", return_value="https://cdn.example/ref.png"), mock.patch.object(client, "_api_request_json", side_effect=TimeoutError("network timeout")) as request:
                with self.assertRaisesRegex(RuntimeError, "uncertain"):
                    client.generate_video(**kwargs)
                with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                    client.generate_video(**kwargs)
                self.assertEqual(request.call_count, 1)
            journal = json.loads((root / "j.json").read_text())
            self.assertEqual(journal["state"], "uncertain")
            self.assertEqual(journal["request_digest"], "digest")
            journal["state"] = "queued"
            journal["request_id"] = "req-3"
            journal["status_url"] = "https://api.higgsfield.ai/requests/req-3/status"
            (root / "j.json").write_text(json.dumps(journal))
            kwargs["poll"] = True
            with mock.patch.object(client, "_api_request_json", return_value={"status": "completed", "request_id": "req-3", "video": {"url": "https://cdn.example/v.mp4"}}) as request, mock.patch("toc.providers.higgsfield.validate_media_url", side_effect=lambda url: url), mock.patch("toc.providers.higgsfield.request_public_media_bytes", return_value=b"ok"):
                result = client.generate_video(**kwargs)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(request.call_args.kwargs["method"], "GET")

    def test_failure_does_not_replace_existing_output_and_digest_is_bound(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / "ref.png"
            ref.write_bytes(b"ref")
            out = root / "out.mp4"
            out.write_bytes(b"approved")
            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            kwargs = dict(model="bytedance/seedance-2.5/reference-to-video", prompt="p", duration_seconds=5, aspect_ratio="16:9", resolution="720p", input_image=None, last_frame_image=None, reference_images=[ref], generate_audio=False, out_path=out, journal_path=root / "j.json", request_digest="digest", poll=False)
            with mock.patch.object(client, "_upload_file", return_value="https://cdn.example/ref.png"), mock.patch.object(client, "_api_request_json", return_value={"status": "failed", "request_id": "r", "error": "private details"}):
                result = client.generate_video(**kwargs)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(out.read_bytes(), b"approved")
            kwargs["request_digest"] = "changed"
            with self.assertRaisesRegex(ValueError, "different request identity"):
                client.generate_video(**kwargs)

    def test_crash_left_submitting_never_reposts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / "ref.png"
            ref.write_bytes(b"ref")
            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            kwargs = dict(model="bytedance/seedance-2.5/reference-to-video", prompt="p", duration_seconds=5, aspect_ratio="16:9", resolution="720p", input_image=None, last_frame_image=None, reference_images=[ref], generate_audio=False, out_path=root / "out.mp4", journal_path=root / "j.json", request_digest="digest", poll=False)
            payload = {"prompt": "p", "duration": 5, "aspect_ratio": "16:9", "resolution": "720p", "image_urls": ["https://cdn.example/ref.png"], "generate_audio": False}
            journal = {"request_digest": "digest", "model": kwargs["model"], "state": "submitting", "payload": payload, "payload_digest": __import__("hashlib").sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "request_fingerprint": client._request_fingerprint(model=kwargs["model"], prompt=kwargs["prompt"], duration_seconds=kwargs["duration_seconds"], aspect_ratio=kwargs["aspect_ratio"], resolution=kwargs["resolution"], input_image=kwargs["input_image"], last_frame_image=kwargs["last_frame_image"], reference_images=kwargs["reference_images"], generate_audio=kwargs["generate_audio"])}
            (root / "j.json").write_text(json.dumps(journal))
            with mock.patch.object(client, "_upload_file", return_value="https://cdn.example/ref.png"), mock.patch.object(client, "_api_request_json") as request:
                with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                    client.generate_video(**kwargs)
            request.assert_not_called()

    def test_changed_input_bytes_with_same_caller_digest_cannot_reuse_journal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / "ref.png"
            ref.write_bytes(b"original")
            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            kwargs = dict(model="bytedance/seedance-2.5/reference-to-video", prompt="p", duration_seconds=5, aspect_ratio="16:9", resolution="720p", input_image=None, last_frame_image=None, reference_images=[ref], generate_audio=False, out_path=root / "out.mp4", journal_path=root / "j.json", request_digest="same", poll=False)
            with mock.patch.object(client, "_upload_file", return_value="https://cdn.example/ref.png"), mock.patch.object(client, "_api_request_json", return_value={"status": "queued", "request_id": "r", "status_url": "https://api.higgsfield.ai/requests/r/status"}):
                client.generate_video(**kwargs)
            ref.write_bytes(b"changed")
            with mock.patch.object(client, "_upload_file") as upload, self.assertRaisesRegex(ValueError, "different request identity"):
                client.generate_video(**kwargs)
            upload.assert_not_called()
            ref.write_bytes(b"original")
            kwargs["prompt"] = "changed settings"
            with mock.patch.object(client, "_upload_file") as upload, self.assertRaisesRegex(ValueError, "different request identity"):
                client.generate_video(**kwargs)
            upload.assert_not_called()
            kwargs["prompt"] = "p"
            ref.write_bytes(b"original")
            journal = json.loads((root / "j.json").read_text())
            journal["payload"]["prompt"] = "tampered"
            (root / "j.json").write_text(json.dumps(journal))
            with mock.patch.object(client, "_api_request_json") as request, self.assertRaisesRegex(ValueError, "integrity"):
                client.generate_video(**kwargs)
            request.assert_not_called()

    def test_completed_journal_without_result_url_fetches_status_again(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / "ref.png"
            ref.write_bytes(b"ref")
            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            kwargs = dict(model="bytedance/seedance-2.5/reference-to-video", prompt="p", duration_seconds=5, aspect_ratio="16:9", resolution="720p", input_image=None, last_frame_image=None, reference_images=[ref], generate_audio=False, out_path=root / "out.mp4", journal_path=root / "j.json", request_digest="digest", poll=False)
            payload = {"prompt": "p", "duration": 5, "aspect_ratio": "16:9", "resolution": "720p", "image_urls": ["https://cdn.example/ref.png"], "generate_audio": False}
            journal = {"request_digest": "digest", "model": kwargs["model"], "state": "completed", "request_id": "r", "status_url": "https://api.higgsfield.ai/requests/r/status", "payload": payload, "payload_digest": __import__("hashlib").sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "request_fingerprint": client._request_fingerprint(model=kwargs["model"], prompt=kwargs["prompt"], duration_seconds=kwargs["duration_seconds"], aspect_ratio=kwargs["aspect_ratio"], resolution=kwargs["resolution"], input_image=kwargs["input_image"], last_frame_image=kwargs["last_frame_image"], reference_images=kwargs["reference_images"], generate_audio=kwargs["generate_audio"])}
            (root / "j.json").write_text(json.dumps(journal))
            with mock.patch.object(client, "_api_request_json", return_value={"status": "completed", "request_id": "r", "video": {"url": "https://cdn.example/v.mp4"}}) as request, mock.patch("toc.providers.higgsfield.validate_media_url", side_effect=lambda url: url), mock.patch("toc.providers.higgsfield.request_public_media_bytes", return_value=b"video"):
                result = client.generate_video(**kwargs)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(request.call_args.kwargs["method"], "GET")
            self.assertEqual((root / "out.mp4").read_bytes(), b"video")

    def test_terminal_failure_is_sanitized_and_saved_status_url_is_restricted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / "ref.png"
            ref.write_bytes(b"ref")
            out = root / "out.mp4"
            out.write_bytes(b"approved")
            client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))
            kwargs = dict(model="bytedance/seedance-2.5/reference-to-video", prompt="p", duration_seconds=5, aspect_ratio="16:9", resolution="720p", input_image=None, last_frame_image=None, reference_images=[ref], generate_audio=False, out_path=out, journal_path=root / "j.json", request_digest="digest", poll=True)
            payload = {"prompt": "p", "duration": 5, "aspect_ratio": "16:9", "resolution": "720p", "image_urls": ["https://cdn.example/ref.png"], "generate_audio": False}
            journal = {"request_digest": "digest", "model": kwargs["model"], "state": "failed", "request_id": "r", "status_url": "https://api.higgsfield.ai.evil.test/requests/r/status", "payload": payload, "payload_digest": __import__("hashlib").sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "request_fingerprint": client._request_fingerprint(model=kwargs["model"], prompt=kwargs["prompt"], duration_seconds=kwargs["duration_seconds"], aspect_ratio=kwargs["aspect_ratio"], resolution=kwargs["resolution"], input_image=kwargs["input_image"], last_frame_image=kwargs["last_frame_image"], reference_images=kwargs["reference_images"], generate_audio=kwargs["generate_audio"])}
            (root / "j.json").write_text(json.dumps(journal))
            with mock.patch.object(client, "_api_request_json") as request:
                result = client.generate_video(**kwargs)
            self.assertEqual(result, {"status": "failed", "request_id": "r", "error": "Generation failed"})
            request.assert_not_called()
            self.assertEqual(out.read_bytes(), b"approved")
            journal["state"] = "queued"
            (root / "j.json").write_text(json.dumps(journal))
            with mock.patch.object(client, "_api_request_json") as request:
                with self.assertRaisesRegex(ValueError, "official HTTPS origin"):
                    client.generate_video(**kwargs)
            request.assert_not_called()
