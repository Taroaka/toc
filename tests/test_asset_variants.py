import hashlib
import pytest
from PIL import Image

from toc import asset_variants
from toc.asset_variants import AssetVariantError, create_variant, list_variants


def _png(path, pixels):
    image = Image.new("RGBA", (4, 3))
    image.putdata(pixels)
    image.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_variant_copies_only_selected_pixels_and_keeps_alpha(tmp_path):
    base_pixels = [(10, 20, 30, (i * 17) % 256) for i in range(12)]
    edited_pixels = [(200, 150, 100, 255 - i) for i in range(12)]
    base_hash = _png(tmp_path / "base.png", base_pixels)
    original_base_bytes = (tmp_path / "base.png").read_bytes()
    edited_hash = _png(tmp_path / "edited.png", edited_pixels)

    record = create_variant(
        tmp_path,
        item_id="char_1",
        base_path="base.png",
        edited_path="edited.png",
        base_sha256=base_hash,
        edited_sha256=edited_hash,
        regions=[{"x": 0.25, "y": 1 / 3, "width": 0.5, "height": 1 / 3}],
        state_description="turn head slightly",
    )

    with Image.open(tmp_path / record["path"]) as result:
        actual = list(result.convert("RGBA").getdata())
    expected = list(base_pixels)
    for y in range(1, 2):
        for x in range(1, 3):
            expected[y * 4 + x] = edited_pixels[y * 4 + x]
    assert actual == expected
    assert (tmp_path / "base.png").read_bytes() == original_base_bytes
    listed = list_variants(tmp_path, "char_1")
    assert len(listed) == 1
    assert listed[0]["stale"] is False
    assert listed[0]["regions"] == [{"x": 1, "y": 1, "width": 2, "height": 1}]


def test_palette_transparency_preserves_displayed_rgba_outside_editable_region(tmp_path):
    base = Image.new("P", (4, 3))
    base.putpalette([255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * (768 - 9))
    base.putdata([0, 1, 2, 0] * 3)
    base.save(tmp_path / "base.png", transparency=0)
    edited = Image.new("P", (4, 3))
    edited.putpalette([0, 255, 255, 255, 255, 0, 255, 0, 255] + [0] * (768 - 9))
    edited.putdata([1, 2, 0, 1] * 3)
    edited.save(tmp_path / "edited.png", transparency=1)
    base_hash = hashlib.sha256((tmp_path / "base.png").read_bytes()).hexdigest()
    edited_hash = hashlib.sha256((tmp_path / "edited.png").read_bytes()).hexdigest()
    with Image.open(tmp_path / "base.png") as source:
        expected = list(source.convert("RGBA").getdata())
    with Image.open(tmp_path / "edited.png") as source:
        edited_pixels = list(source.convert("RGBA").getdata())

    record = create_variant(
        tmp_path,
        item_id="palette_item",
        base_path="base.png",
        edited_path="edited.png",
        base_sha256=base_hash,
        edited_sha256=edited_hash,
        regions=[{"x": 0, "y": 0, "width": 0.25, "height": 1}],
        state_description="change left column",
    )
    with Image.open(tmp_path / record["path"]) as result:
        actual = list(result.convert("RGBA").getdata())
    expected = [edited_pixels[i] if i % 4 == 0 else expected[i] for i in range(12)]
    assert actual == expected


def test_source_drift_during_composition_aborts_publication(tmp_path, monkeypatch):
    base_hash = _png(tmp_path / "base.png", [(0, 0, 0, 255)] * 12)
    edited_hash = _png(tmp_path / "edited.png", [(1, 1, 1, 255)] * 12)
    original_pixel_box = asset_variants._pixel_box

    def mutate_edited(region, width, height):
        (tmp_path / "edited.png").write_bytes(b"changed during composition")
        return original_pixel_box(region, width, height)

    monkeypatch.setattr(asset_variants, "_pixel_box", mutate_edited)
    with pytest.raises(AssetVariantError, match="changed while composing"):
        create_variant(
            tmp_path,
            item_id="item",
            base_path="base.png",
            edited_path="edited.png",
            base_sha256=base_hash,
            edited_sha256=edited_hash,
            regions=[{"x": 0, "y": 0, "width": 1, "height": 1}],
            state_description="changed",
        )
    output_dir = tmp_path / "assets/test/state_variants/item"
    assert not output_dir.exists() or not list(output_dir.iterdir())


@pytest.mark.parametrize(
    "region",
    [
        {"x": 0, "y": 0, "width": 0, "height": 0.5},
        {"x": -0.1, "y": 0, "width": 0.2, "height": 0.2},
        {"x": 0.9, "y": 0.9, "width": 0.2, "height": 0.2},
        {"x": float("nan"), "y": 0, "width": 0.2, "height": 0.2},
    ],
)
def test_rejects_empty_or_outside_regions(tmp_path, region):
    base_hash = _png(tmp_path / "base.png", [(0, 0, 0, 255)] * 12)
    edited_hash = _png(tmp_path / "edited.png", [(1, 1, 1, 255)] * 12)
    with pytest.raises(AssetVariantError):
        create_variant(
            tmp_path,
            item_id="item",
            base_path="base.png",
            edited_path="edited.png",
            base_sha256=base_hash,
            edited_sha256=edited_hash,
            regions=[region],
            state_description="changed",
        )


def test_rejects_stale_hash_dimensions_and_path_escape(tmp_path):
    base_hash = _png(tmp_path / "base.png", [(0, 0, 0, 255)] * 12)
    edited_hash = _png(tmp_path / "edited.png", [(1, 1, 1, 255)] * 12)
    Image.new("RGB", (2, 2)).save(tmp_path / "small.png")
    common = dict(
        root=tmp_path,
        item_id="item",
        base_path="base.png",
        edited_path="edited.png",
        base_sha256=base_hash,
        edited_sha256=edited_hash,
        regions=[{"x": 0, "y": 0, "width": 1, "height": 1}],
        state_description="changed",
    )
    with pytest.raises(AssetVariantError, match="stale"):
        create_variant(**{**common, "edited_sha256": "0" * 64})
    with pytest.raises(AssetVariantError, match="dimensions"):
        create_variant(**{**common, "edited_path": "small.png", "edited_sha256": hashlib.sha256((tmp_path / "small.png").read_bytes()).hexdigest()})
    with pytest.raises(AssetVariantError, match="run-relative"):
        create_variant(**{**common, "base_path": "../outside.png"})


def test_list_variants_reports_changed_source_and_output_as_stale(tmp_path):
    base_hash = _png(tmp_path / "base.png", [(0, 0, 0, 255)] * 12)
    edited_hash = _png(tmp_path / "edited.png", [(1, 1, 1, 255)] * 12)
    record = create_variant(
        tmp_path,
        item_id="item",
        base_path="base.png",
        edited_path="edited.png",
        base_sha256=base_hash,
        edited_sha256=edited_hash,
        regions=[{"x": 0, "y": 0, "width": 1, "height": 1}],
        state_description="changed",
    )
    (tmp_path / "edited.png").write_bytes(b"replaced")
    (tmp_path / record["path"]).write_bytes(b"replaced output")
    assert list_variants(tmp_path, "item")[0]["stale"] is True
