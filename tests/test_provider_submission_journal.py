from __future__ import annotations

import multiprocessing
import os
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import image_gen_app
from toc.provider_submission_journal import (
    UnknownSubmissionStateError,
    provider_submission_scope,
    submit_provider_request,
)


def _concurrent_submit_worker(
    root_path: str,
    barrier: multiprocessing.synchronize.Barrier,
    count_path: str,
    result_queue: multiprocessing.queues.Queue,
) -> None:
    barrier.wait(timeout=10)

    def submit() -> dict[str, object]:
        with Path(count_path).open("a", encoding="utf-8") as stream:
            stream.write("submit\n")
            stream.flush()
        time.sleep(0.2)
        return {"data": {"id": "provider-task-1"}}

    with provider_submission_scope(
        Path(root_path), provider="kling", scope="candidate-01"
    ):
        _response, operation_id = submit_provider_request(
            provider="kling",
            payload={"model": "reviewed-model", "prompt": "private prompt"},
            endpoint="https://provider.example/video",
            submit=submit,
            extract_id=lambda response: str(response["data"]["id"]),
        )
    result_queue.put(operation_id)


class TestProviderSubmissionJournal(unittest.TestCase):
    def test_kling_and_seedance_resume_polling_without_resubmitting(self) -> None:
        for provider in ("kling", "seedance"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                destination = run_dir / "candidate.mp4"
                submitted_ids: list[str] = []
                polled_ids: list[str] = []

                if provider == "kling":
                    class FakeClient:
                        def __init__(self, config):
                            self.config = config
                            self._last_status_path_template = None

                        def build_video_payload(self, **kwargs):
                            return kwargs

                        def start_video_generation(self, **_kwargs):
                            submitted_ids.append("kling-task-1")
                            return {"data": {"id": "kling-task-1"}}

                        def extract_operation_id(self, response):
                            return response["data"]["id"]

                        def poll_operation(self, *, operation_id_or_url, **_kwargs):
                            polled_ids.append(operation_id_or_url)
                            self_outer.assertEqual(
                                self._last_status_path_template,
                                "/v1/videos/text2video/{operation_id}",
                            )
                            journal = next((run_dir / "logs" / "providers" / "kling_submissions").glob("*.json"))
                            self_outer.assertIn('"state":"accepted"', journal.read_text(encoding="utf-8"))
                            if len(polled_ids) == 1:
                                raise TimeoutError("poll interrupted")
                            return {"status": "succeeded"}

                        def is_failed_operation(self, _operation):
                            return False

                        def extract_video_uri(self, _operation):
                            return "https://provider.example/video.mp4"

                        def download_to_file(self, *, out_path, **_kwargs):
                            out_path.write_bytes(b"video")

                    tool = "kling_3_0"
                    model = "kling-3.0"
                    patch_client = patch("server.image_gen_app.KlingClient", FakeClient)
                    env = {"KLING_API_KEY": "test-key"}
                else:
                    class FakeClient:
                        def __init__(self, config):
                            self.config = config

                        def build_video_payload(self, **kwargs):
                            return kwargs

                        def create_task(self, *, payload):
                            submitted_ids.append("seedance-task-1")
                            return {"id": "seedance-task-1"}

                        def extract_task_id(self, response):
                            return response["id"]

                        def poll_task(self, *, task_id, **_kwargs):
                            polled_ids.append(task_id)
                            journal = next((run_dir / "logs" / "providers" / "seedance_submissions").glob("*.json"))
                            self_outer.assertIn('"state":"accepted"', journal.read_text(encoding="utf-8"))
                            if len(polled_ids) == 1:
                                raise TimeoutError("poll interrupted")
                            return {"status": "succeeded"}

                        def is_failed_task(self, _task):
                            return False

                        def extract_video_url(self, _task):
                            return "https://provider.example/video.mp4"

                        def download_to_file(self, *, out_path, **_kwargs):
                            out_path.write_bytes(b"video")

                    tool = "seedance"
                    model = "seedance-1-0-pro-250528"
                    patch_client = patch("server.image_gen_app.SeedanceClient", FakeClient)
                    env = {"ARK_API_KEY": "test-key"}

                self_outer = self
                request = image_gen_app.VideoGenerateItem(
                    item_id="scene10_cut1",
                    prompt="reviewed prompt",
                    tool=tool,
                    duration_seconds=6,
                    provider_execution_options={"model": model},
                )
                with patch.dict(os.environ, env, clear=False), patch_client:
                    with self.assertRaisesRegex(TimeoutError, "poll interrupted"):
                        image_gen_app._generate_video_file_blocking(
                            run_dir=run_dir,
                            request=request,
                            index=1,
                            destination=destination,
                            input_image=None,
                            last_frame_image=None,
                            reference_images=[],
                        )
                    result = image_gen_app._generate_video_file_blocking(
                        run_dir=run_dir,
                        request=request,
                        index=1,
                        destination=destination,
                        input_image=None,
                        last_frame_image=None,
                        reference_images=[],
                    )

                self.assertEqual(result["status"], "completed")
                self.assertEqual(len(submitted_ids), 1)
                self.assertEqual(polled_ids, [submitted_ids[0], submitted_ids[0]])

    def test_persists_intent_before_post_and_keeps_ambiguous_attempt_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = 0

            def submit() -> dict[str, object]:
                nonlocal calls
                calls += 1
                journal_files = list(
                    (root / "logs" / "providers").rglob("*.json")
                )
                self.assertEqual(len(journal_files), 1)
                before_post = journal_files[0].read_text(encoding="utf-8")
                self.assertIn('"state":"intent"', before_post)
                self.assertNotIn("private prompt", before_post)
                self.assertNotIn("provider-secret", before_post)
                raise TimeoutError("connection dropped after provider accepted")

            with provider_submission_scope(
                root, provider="seedance", scope="candidate-01"
            ):
                with self.assertRaisesRegex(TimeoutError, "connection dropped"):
                    submit_provider_request(
                        provider="seedance",
                        payload={
                            "model": "reviewed-model",
                            "prompt": "private prompt",
                            "api_key": "provider-secret",
                        },
                        endpoint="https://provider.example/tasks",
                        submit=submit,
                        extract_id=lambda response: str(response["id"]),
                    )

            with provider_submission_scope(
                root, provider="seedance", scope="candidate-01"
            ):
                with self.assertRaises(UnknownSubmissionStateError):
                    submit_provider_request(
                        provider="seedance",
                        payload={
                            "model": "reviewed-model",
                            "prompt": "private prompt",
                            "api_key": "provider-secret",
                        },
                        endpoint="https://provider.example/tasks",
                        submit=lambda: self.fail("ambiguous requests must not be reposted"),
                        extract_id=lambda response: str(response["id"]),
                    )

            self.assertEqual(calls, 1)
            contents = "".join(
                path.read_text(encoding="utf-8")
                for path in (root / "logs" / "providers").rglob("*.json")
            )
            self.assertNotIn("private prompt", contents)
            self.assertNotIn("provider-secret", contents)

    def test_reuses_accepted_operation_id_for_the_same_scoped_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = 0

            def submit() -> dict[str, object]:
                nonlocal calls
                calls += 1
                return {"data": {"id": "provider-task-2"}}

            with provider_submission_scope(
                root, provider="kling", scope="candidate-01"
            ):
                response, operation_id = submit_provider_request(
                    provider="kling",
                    payload={"model": "reviewed-model", "prompt": "private prompt"},
                    endpoint="https://provider.example/video",
                    submit=submit,
                    extract_id=lambda item: str(item["data"]["id"]),
                )
            self.assertEqual(operation_id, "provider-task-2")
            self.assertEqual(response["data"]["id"], "provider-task-2")

            with provider_submission_scope(
                root, provider="kling", scope="candidate-01"
            ):
                resumed, resumed_id = submit_provider_request(
                    provider="kling",
                    payload={"model": "reviewed-model", "prompt": "private prompt"},
                    endpoint="https://provider.example/video",
                    submit=lambda: self.fail("accepted work must resume by polling its id"),
                    extract_id=lambda item: str(item["data"]["id"]),
                )

            self.assertEqual(resumed_id, "provider-task-2")
            self.assertEqual(resumed["data"]["id"], "provider-task-2")
            self.assertEqual(calls, 1)

    def test_changed_payload_or_candidate_scope_gets_a_new_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            submissions: list[str] = []

            def run(scope: str, prompt: str) -> None:
                with provider_submission_scope(root, provider="kling", scope=scope):
                    submit_provider_request(
                        provider="kling",
                        payload={"model": "reviewed-model", "prompt": prompt},
                        endpoint="https://provider.example/video",
                        submit=lambda: submissions.append(scope + ":" + prompt)
                        or {"id": f"task-{len(submissions)}"},
                        extract_id=lambda response: str(response["id"]),
                    )

            run("candidate-01", "same prompt")
            run("candidate-02", "same prompt")
            run("candidate-01", "changed prompt")

            self.assertEqual(
                submissions,
                [
                    "candidate-01:same prompt",
                    "candidate-02:same prompt",
                    "candidate-01:changed prompt",
                ],
            )

    def test_cross_process_submits_once_for_one_request_hash(self) -> None:
        context = multiprocessing.get_context("fork")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            counter = root / "submit-count.txt"
            barrier = context.Barrier(2)
            result_queue = context.Queue()
            workers = [
                context.Process(
                    target=_concurrent_submit_worker,
                    args=(str(root), barrier, str(counter), result_queue),
                )
                for _ in range(2)
            ]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=15)

            self.assertEqual([worker.exitcode for worker in workers], [0, 0])
            self.assertEqual(
                [result_queue.get(timeout=2), result_queue.get(timeout=2)],
                ["provider-task-1", "provider-task-1"],
            )
            self.assertEqual(counter.read_text(encoding="utf-8").splitlines(), ["submit"])

    def test_rejects_symlinked_journal_parent(self) -> None:
        for parent_name in ("logs", ".locks"):
            with self.subTest(parent=parent_name), tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
                root = Path(tmp)
                (root / parent_name).symlink_to(outside, target_is_directory=True)
                with provider_submission_scope(
                    root, provider="kling", scope="candidate-01"
                ):
                    with self.assertRaises((OSError, ValueError, RuntimeError)):
                        submit_provider_request(
                            provider="kling",
                            payload={"model": "reviewed-model"},
                            endpoint="https://provider.example/video",
                            submit=lambda: self.fail("unsafe journal path must fail before POST"),
                            extract_id=lambda response: str(response["id"]),
                        )


if __name__ == "__main__":
    unittest.main()
