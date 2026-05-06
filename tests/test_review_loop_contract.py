from __future__ import annotations

import importlib
import unittest
from dataclasses import asdict, is_dataclass
from typing import Any


def _load_review_loop_module() -> Any:
    module_names = (
        "toc.review_loop",
        "toc.review_loop_contract",
        "toc.stage_review_loop",
    )
    errors: list[str] = []
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            errors.append(f"{module_name}: {exc}")
    raise AssertionError("Expected a review-loop helper module. Tried: " + ", ".join(errors))


def _public_contract(module: Any, stage: str) -> Any:
    for function_name in (
        "build_review_loop_contract",
        "make_review_loop_contract",
        "review_loop_contract",
        "build_stage_review_loop",
    ):
        function = getattr(module, function_name, None)
        if callable(function):
            return function(stage)

    for class_name in ("ReviewLoopContract", "ReviewLoopConfig"):
        cls = getattr(module, class_name, None)
        if cls is None:
            continue
        if hasattr(cls, "for_stage"):
            return cls.for_stage(stage)
        try:
            return cls(stage=stage)
        except TypeError:
            return cls()

    if hasattr(module, "REVIEW_LOOP_SPECS") or hasattr(module, "MAX_REVIEW_LOOP_ROUNDS"):
        return module

    raise AssertionError("Expected a public review-loop contract builder or config class.")


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {key: _plain(item) for key, item in vars(value).items() if not key.startswith("_")}
    return value


def _find_value(value: Any, key: str) -> Any:
    plain = _plain(value)
    if isinstance(plain, dict):
        if key in plain:
            return plain[key]
        for item in plain.values():
            found = _find_value(item, key)
            if found is not None:
                return found
    if isinstance(plain, list):
        for item in plain:
            found = _find_value(item, key)
            if found is not None:
                return found
    return None


def _collect_strings(value: Any) -> list[str]:
    plain = _plain(value)
    if isinstance(plain, str):
        return [plain]
    if isinstance(plain, dict):
        strings: list[str] = []
        for key, item in plain.items():
            strings.append(str(key))
            strings.extend(_collect_strings(item))
        return strings
    if isinstance(plain, list):
        strings: list[str] = []
        for item in plain:
            strings.extend(_collect_strings(item))
        return strings
    return [str(plain)]


def _state_updates(module: Any, contract: Any, stage: str) -> dict[str, Any]:
    for function_name in (
        "loop_state_updates",
        "review_loop_state_updates",
        "build_review_loop_state_updates",
        "make_review_loop_state_updates",
    ):
        function = getattr(module, function_name, None)
        if callable(function):
            try:
                return _plain(function(stage))
            except TypeError:
                return _plain(function(stage=stage, status="running", current_round=1))

    updates = _find_value(contract, "state_updates")
    if isinstance(updates, dict):
        return _plain(updates)

    raise AssertionError("Expected review-loop helper to expose state updates.")


class TestReviewLoopContract(unittest.TestCase):
    def test_review_loop_defaults_and_artifacts(self) -> None:
        module = _load_review_loop_module()
        contract = _public_contract(module, "story")

        max_rounds = getattr(module, "MAX_REVIEW_LOOP_ROUNDS", None)
        if max_rounds is None:
            max_rounds = _find_value(contract, "max_rounds")
        critic_count = getattr(module, "REVIEW_LOOP_CRITIC_COUNT", None)
        if critic_count is None:
            critic_count = _find_value(contract, "critic_count")
        self.assertEqual(max_rounds, 5)
        self.assertEqual(critic_count, 5)

        critic_relpath = getattr(module, "critic_relpath", None)
        critic_prompt_relpath = getattr(module, "critic_prompt_relpath", None)
        aggregated_review_relpath = getattr(module, "aggregated_review_relpath", None)
        if callable(critic_relpath) and callable(aggregated_review_relpath):
            self.assertEqual(str(critic_relpath("story", 1, 1)), "logs/eval/story/round_01/critic_1.md")
            self.assertTrue(callable(critic_prompt_relpath))
            self.assertEqual(str(critic_prompt_relpath("story", 1, 1)), "logs/eval/story/round_01/prompts/critic_1.prompt.md")
            self.assertEqual(str(aggregated_review_relpath("story", 1)), "logs/eval/story/round_01/aggregated_review.md")
        else:
            rendered = "\n".join(_collect_strings(contract))
            self.assertIn("logs/eval/story/round_01/critic_1.md", rendered)
            self.assertIn("logs/eval/story/round_01/prompts/critic_1.prompt.md", rendered)
            self.assertIn("logs/eval/story/round_01/aggregated_review.md", rendered)

    def test_review_loop_state_updates_are_under_eval_stage_loop(self) -> None:
        module = _load_review_loop_module()
        contract = _public_contract(module, "story")

        updates = _state_updates(module, contract, "story")
        loop_updates = {key: value for key, value in updates.items() if key.startswith("eval.story.loop.")}

        self.assertGreaterEqual(len(loop_updates), 3)
        self.assertEqual(str(loop_updates.get("eval.story.loop.max_rounds")), "5")


if __name__ == "__main__":
    unittest.main()
