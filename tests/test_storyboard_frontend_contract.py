from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_TSX = REPO_ROOT / "server" / "web" / "src" / "main.tsx"


def _create_run_source() -> str:
    source = MAIN_TSX.read_text(encoding="utf-8")
    start = source.index("  const createRun = async () => {")
    end = source.index("\n  const sendChat = async () => {", start)
    return source[start:end]


def test_storyboard_frontend_uses_dedicated_endpoint_and_closes_before_post() -> None:
    source = _create_run_source()

    assert "'/api/image-gen/runs/create/storyboard'" in source
    assert source.index("setCreateRunOpen(false);") < source.index(
        "await jsonFetch<CreateRunJob>(endpoint"
    )


def test_storyboard_frontend_does_not_claim_one_scene_always_equals_one_board() -> None:
    source = MAIN_TSX.read_text(encoding="utf-8")

    assert "1scene=1ストーリーボード式" not in source
    assert "scene単位ストーリーボード式（尺に応じて分割）" in source
