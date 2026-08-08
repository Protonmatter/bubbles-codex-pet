#!/usr/bin/env python3
"""Deterministically assemble the Bubbles v2 pet from approved source cells."""

from __future__ import annotations

import argparse
import json
import subprocess
from importlib import resources
from pathlib import Path

from PIL import Image, ImageDraw

CELL = (192, 208)
ATLAS = (1536, 2288)
ROWS = [
    ("idle", 6),
    ("running-right", 8),
    ("running-left", 8),
    ("waving", 4),
    ("jumping", 5),
    ("failed", 8),
    ("waiting", 6),
    ("running", 6),
    ("review", 6),
]
ROW_DURATION_MS = 110
ALL_STATES_DURATION_MS = 90
LOOK_DURATION_MS = 100


def load_cell(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.size != CELL:
        raise ValueError(f"{path}: expected {CELL}, found {image.size}")
    return image


def build_atlas(rows_dir: Path, look_dir: Path) -> Image.Image:
    atlas = Image.new("RGBA", ATLAS, (0, 0, 0, 0))
    for row, (state, count) in enumerate(ROWS):
        for column in range(count):
            cell = load_cell(rows_dir / state / f"{column:02d}.png")
            atlas.alpha_composite(cell, (column * CELL[0], row * CELL[1]))
    for index in range(16):
        cell = load_cell(look_dir / f"{index:02d}.png")
        row, column = 9 + index // 8, index % 8
        atlas.alpha_composite(cell, (column * CELL[0], row * CELL[1]))
    return atlas


def make_contact_sheet(atlas: Image.Image, output: Path) -> None:
    scale = 0.5
    cell_w, cell_h = int(CELL[0] * scale), int(CELL[1] * scale)
    sheet = Image.new("RGBA", (cell_w * 8, cell_h * 11 + 22 * 11), "white")
    draw = ImageDraw.Draw(sheet)
    names = [name for name, _ in ROWS] + ["look 000–157.5", "look 180–337.5"]
    for row, name in enumerate(names):
        y = row * (cell_h + 22)
        draw.text((5, y + 3), f"{row:02d} {name}", fill="black")
        for column in range(8):
            cell = atlas.crop((
                column * CELL[0], row * CELL[1],
                (column + 1) * CELL[0], (row + 1) * CELL[1],
            )).resize((cell_w, cell_h), Image.Resampling.LANCZOS)
            sheet.alpha_composite(cell, (column * cell_w, y + 22))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(output, optimize=False)


def atlas_frames(atlas: Image.Image, row: int, count: int) -> list[Image.Image]:
    return [atlas.crop((i * CELL[0], row * CELL[1], (i + 1) * CELL[0], (row + 1) * CELL[1])) for i in range(count)]


def save_animation(frames: list[Image.Image], output: Path, duration: int) -> None:
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        disposal=2,
        optimize=False,
    )


def save_mp4(gif_path: Path, output: Path) -> None:
    binary_dir = resources.files("imageio_ffmpeg.binaries")
    candidates = sorted(
        (
            entry
            for entry in binary_dir.iterdir()
            if entry.is_file() and entry.name.casefold().startswith("ffmpeg-")
        ),
        key=lambda entry: entry.name.casefold(),
    )
    if len(candidates) != 1:
        raise RuntimeError(
            "expected exactly one FFmpeg executable packaged by imageio-ffmpeg; "
            f"found {len(candidates)}"
        )

    with resources.as_file(candidates[0]) as ffmpeg:
        subprocess.run([
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(gif_path), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-metadata", "creation_time=1970-01-01T00:00:00Z",
            str(output),
        ], check=True)


def save_previews(atlas: Image.Image, preview_dir: Path) -> None:
    row_dir = preview_dir / "rows"
    row_dir.mkdir(parents=True, exist_ok=True)
    all_frames: list[Image.Image] = []
    for row, (state, count) in enumerate(ROWS):
        frames = atlas_frames(atlas, row, count)
        save_animation(frames, row_dir / f"{state}.gif", ROW_DURATION_MS)
        all_frames.extend(frames)
    all_states_gif = preview_dir / "bubbles-animation-preview.gif"
    look_gif = preview_dir / "bubbles-look-loop.gif"
    save_animation(all_frames, all_states_gif, ALL_STATES_DURATION_MS)
    look = atlas_frames(atlas, 9, 8) + atlas_frames(atlas, 10, 8)
    save_animation(look, look_gif, LOOK_DURATION_MS)
    idle_jump_idle = atlas_frames(atlas, 0, 1) + atlas_frames(atlas, 4, 5) + atlas_frames(atlas, 0, 1)
    save_animation(idle_jump_idle, preview_dir / "bubbles-idle-jump-idle.gif", ROW_DURATION_MS)
    save_mp4(all_states_gif, preview_dir / "bubbles-animation-preview.mp4")
    save_mp4(look_gif, preview_dir / "bubbles-look-loop.mp4")
    manifest = {
        "source": "bubbles/spritesheet.png",
        "rowDurationMs": ROW_DURATION_MS,
        "allStatesDurationMs": ALL_STATES_DURATION_MS,
        "lookDurationMs": LOOK_DURATION_MS,
        "allStatesFrames": sum(count for _, count in ROWS),
        "lookFrames": 16,
        "idleJumpIdleFrames": 7,
    }
    (preview_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows-dir", type=Path, default=root / "source/rows")
    parser.add_argument("--look-dir", type=Path, default=root / "source/look-directions")
    parser.add_argument("--out-dir", type=Path, default=root / "bubbles")
    parser.add_argument("--preview-dir", type=Path, default=root / "preview")
    parser.add_argument("--animation-map", type=Path, default=root / "docs/animation-map.json")
    args = parser.parse_args()

    atlas = build_atlas(args.rows_dir, args.look_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    atlas.save(args.out_dir / "spritesheet.png", optimize=False, compress_level=9)
    atlas.save(args.out_dir / "spritesheet.webp", format="WEBP", lossless=True, method=6, exact=True)
    pet = {
        "id": "bubbles",
        "displayName": "Bubbles",
        "description": "A bright, fluffy white Codex companion in her red waistcoat and pink heart collar.",
        "spritesheetPath": "spritesheet.png",
    }
    (args.out_dir / "pet.json").write_text(
        json.dumps(pet, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    make_contact_sheet(atlas, args.preview_dir / "bubbles-contact-sheet.png")
    save_previews(atlas, args.preview_dir)
    if not args.animation_map.exists():
        raise FileNotFoundError(args.animation_map)
    print(args.out_dir / "spritesheet.png")


if __name__ == "__main__":
    main()
