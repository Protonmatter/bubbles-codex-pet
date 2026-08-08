#!/usr/bin/env python3
"""Compare committed runtime and previews with a fresh deterministic rebuild."""

from __future__ import annotations

import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageChops, ImageSequence, ImageStat

MAX_MP4_FRAME_MAE = 4.0
MAX_MP4_BLOCK_MAE = 12.0
MP4_BLOCK_SIZE = 16


def image_pixels(path: Path) -> tuple[tuple[int, int], list[bytes], list[int]]:
    with Image.open(path) as image:
        frames = [frame.convert("RGBA").tobytes() for frame in ImageSequence.Iterator(image)]
        durations = [int(frame.info.get("duration", 0)) for frame in ImageSequence.Iterator(image)]
        return image.size, frames, durations


def probe_video(path: Path) -> tuple[dict[str, object], list[bytes]]:
    reader = imageio_ffmpeg.read_frames(str(path))
    try:
        metadata = next(reader)
        decoded = list(reader)
    finally:
        reader.close()
    frames, seconds = imageio_ffmpeg.count_frames_and_secs(str(path))
    if len(decoded) != frames:
        raise ValueError(f"{path}: decoded {len(decoded)} frames but FFmpeg counted {frames}")
    properties = {
        "size": list(metadata["size"]),
        "fps": round(float(metadata["fps"]), 3),
        "frames": frames,
        "duration": round(seconds, 3),
    }
    return properties, decoded


def frame_errors(committed: bytes, rebuilt: bytes, size: tuple[int, int]) -> tuple[float, float]:
    expected_bytes = size[0] * size[1] * 3
    if len(committed) != expected_bytes or len(rebuilt) != expected_bytes:
        raise ValueError(f"decoded RGB frame size differs from {size}: {len(committed)} != {len(rebuilt)}")
    difference = ImageChops.difference(
        Image.frombytes("RGB", size, committed),
        Image.frombytes("RGB", size, rebuilt),
    )
    frame_mae = sum(ImageStat.Stat(difference).mean) / 3
    block_map = difference.resize(
        (size[0] // MP4_BLOCK_SIZE, size[1] // MP4_BLOCK_SIZE),
        Image.Resampling.BOX,
    )
    block_mae = max(sum(pixel) / 3 for pixel in block_map.get_flattened_data())
    return frame_mae, block_mae


def compare_video(committed_path: Path, rebuilt_path: Path) -> None:
    committed_properties, committed_frames = probe_video(committed_path)
    rebuilt_properties, rebuilt_frames = probe_video(rebuilt_path)
    if committed_properties != rebuilt_properties:
        raise SystemExit(
            f"rebuilt {rebuilt_path} properties differ: "
            f"{committed_properties} != {rebuilt_properties}"
        )
    width, height = committed_properties["size"]
    size = int(width), int(height)
    for index, (committed, rebuilt) in enumerate(zip(committed_frames, rebuilt_frames, strict=True)):
        frame_mae, block_mae = frame_errors(committed, rebuilt, size)
        if frame_mae > MAX_MP4_FRAME_MAE or block_mae > MAX_MP4_BLOCK_MAE:
            raise SystemExit(
                f"rebuilt {rebuilt_path} decoded frame {index} differs: "
                f"mean error {frame_mae:.3f}, max block error {block_mae:.3f}"
            )


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit("usage: check_reproducibility.py COMMITTED_PET COMMITTED_PREVIEW REBUILT_PET REBUILT_PREVIEW")
    committed_pet, committed_preview, rebuilt_pet, rebuilt_preview = map(Path, sys.argv[1:])

    if (committed_pet / "pet.json").read_bytes() != (rebuilt_pet / "pet.json").read_bytes():
        raise SystemExit("rebuilt pet.json differs")

    image_paths = [
        "spritesheet.png", "spritesheet.webp",
    ]
    for relative in image_paths:
        if image_pixels(committed_pet / relative) != image_pixels(rebuilt_pet / relative):
            raise SystemExit(f"rebuilt {relative} differs")

    preview_images = [
        "bubbles-contact-sheet.png", "bubbles-animation-preview.gif",
        "bubbles-look-loop.gif", "bubbles-idle-jump-idle.gif",
    ] + [f"rows/{name}.gif" for name in (
        "idle", "running-right", "running-left", "waving", "jumping",
        "failed", "waiting", "running", "review",
    )]
    for relative in preview_images:
        if image_pixels(committed_preview / relative) != image_pixels(rebuilt_preview / relative):
            raise SystemExit(f"rebuilt preview/{relative} differs")

    if (committed_preview / "manifest.json").read_bytes() != (rebuilt_preview / "manifest.json").read_bytes():
        raise SystemExit("rebuilt preview manifest differs")
    for relative in ["bubbles-animation-preview.mp4", "bubbles-look-loop.mp4"]:
        compare_video(committed_preview / relative, rebuilt_preview / relative)
    print("Runtime metadata, atlas, WebP, GIF timing/pixels, and MP4 properties/content reproduce")


if __name__ == "__main__":
    main()
