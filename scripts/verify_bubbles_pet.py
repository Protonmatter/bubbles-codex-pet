#!/usr/bin/env python3
"""Verify the approved Bubbles runtime package and Codex v2 atlas contract."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

CELL = (192, 208)
ATLAS = (1536, 2288)
COUNTS = [6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]
EXPECTED_METADATA = {
    "id": "bubbles",
    "displayName": "Bubbles",
    "description": "A bright, fluffy white Codex companion in her red waistcoat and pink heart collar.",
    "spritesheetPath": "spritesheet.png",
}
APPROVED_PIXEL_SHA256 = "1620a4b6d07c6650c4bae79491529de57729804f968f36f0b6faf20d63a46d12"


def fail(message: str) -> None:
    raise SystemExit(message)


def bbox_alpha(cell: Image.Image):
    return cell.getchannel("A").getbbox()


def atlas_cell(atlas: Image.Image, row: int, column: int) -> Image.Image:
    return atlas.crop((
        column * CELL[0], row * CELL[1],
        (column + 1) * CELL[0], (row + 1) * CELL[1],
    ))


def verify(package: Path) -> dict[str, object]:
    metadata_path = package / "pet.json"
    atlas_path = package / "spritesheet.png"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata != EXPECTED_METADATA:
        fail("pet.json differs from the approved Bubbles metadata")
    if atlas_path.stat().st_size >= 20 * 1024 * 1024:
        fail("spritesheet exceeds the 20 MiB limit")

    with Image.open(atlas_path) as encoded:
        if encoded.format != "PNG" or encoded.mode != "RGBA" or encoded.size != ATLAS:
            fail(f"expected RGBA PNG {ATLAS}, found {encoded.format} {encoded.mode} {encoded.size}")
        atlas = encoded.copy()

    encoded_sha256 = hashlib.sha256(atlas_path.read_bytes()).hexdigest()
    pixel_sha256 = hashlib.sha256(atlas.tobytes()).hexdigest()
    if pixel_sha256 != APPROVED_PIXEL_SHA256:
        fail(
            "spritesheet pixels differ from the approved Bubbles atlas "
            f"(expected {APPROVED_PIXEL_SHA256}, found {pixel_sha256})"
        )

    required = 0
    unused = 0
    variations: dict[str, int] = {}
    frame_bounds: dict[str, list[int]] = {}
    for row, count in enumerate(COUNTS):
        hashes = set()
        for column in range(8):
            cell = atlas_cell(atlas, row, column)
            box = bbox_alpha(cell)
            if column < count:
                required += 1
                if box is None:
                    fail(f"required cell r{row}c{column} is empty")
                if box[0] == 0 or box[1] == 0 or box[2] == CELL[0] or box[3] == CELL[1]:
                    fail(f"required cell r{row}c{column} touches a cell edge")
                hashes.add(ImageChops.difference(cell, Image.new("RGBA", CELL)).tobytes())
                frame_bounds[f"r{row}c{column}"] = list(box)
            else:
                unused += 1
                if box is not None:
                    fail(f"unused cell r{row}c{column} contains artwork")
        minimum_variation = 2 if row < 9 else count
        if len(hashes) < minimum_variation:
            fail(f"row {row} lacks required frame variation")
        variations[str(row)] = len(hashes)

    jump_bottoms = [frame_bounds[f"r4c{column}"][3] for column in range(COUNTS[4])]
    jump_lift = max(jump_bottoms[0], jump_bottoms[-1]) - min(jump_bottoms[1:-1])
    if jump_lift < 20 or abs(jump_bottoms[0] - jump_bottoms[-1]) > 8:
        fail("jump row does not visibly lift and return to its baseline")

    hidden_rgb = 0
    for r, g, b, a in atlas.get_flattened_data():
        if a == 0 and (r or g or b):
            hidden_rgb += 1
    if hidden_rgb:
        fail(f"{hidden_rgb} fully transparent pixels retain hidden RGB")

    return {
        "ok": True,
        "file": "bubbles/spritesheet.png",
        "sha256": encoded_sha256,
        "pixelSha256": pixel_sha256,
        "width": atlas.width,
        "height": atlas.height,
        "spriteVersion": 2,
        "requiredFrames": required,
        "unusedCells": unused,
        "framesPerRow": COUNTS,
        "variationCounts": variations,
        "jumpLiftPixels": jump_lift,
        "bytes": atlas_path.stat().st_size,
    }


def main() -> None:
    package = Path(sys.argv[1] if len(sys.argv) > 1 else "bubbles").resolve()
    report = verify(package)
    if len(sys.argv) > 2:
        output = Path(sys.argv[2])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
