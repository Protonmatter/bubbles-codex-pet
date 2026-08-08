from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify_bubbles_pet.py")
VERIFY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(VERIFY)

BUILD_SPEC = importlib.util.spec_from_file_location("build", ROOT / "scripts/build_bubbles_pet.py")
BUILD = importlib.util.module_from_spec(BUILD_SPEC)
assert BUILD_SPEC.loader
BUILD_SPEC.loader.exec_module(BUILD)

REPRO_SPEC = importlib.util.spec_from_file_location("repro", ROOT / "scripts/check_reproducibility.py")
REPRO = importlib.util.module_from_spec(REPRO_SPEC)
assert REPRO_SPEC.loader
REPRO_SPEC.loader.exec_module(REPRO)


class BubblesHardeningTests(unittest.TestCase):
    def make_package(self, directory: Path) -> Image.Image:
        (directory / "pet.json").write_bytes((ROOT / "bubbles/pet.json").read_bytes())
        return Image.open(ROOT / "bubbles/spritesheet.png").copy()

    def assert_atlas_rejected(self, mutate):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            atlas = self.make_package(package)
            mutate(atlas)
            atlas.save(package / "spritesheet.png", optimize=False, compress_level=9)
            with self.assertRaises(SystemExit):
                VERIFY.verify(package)

    def test_committed_package_passes(self):
        self.assertTrue(VERIFY.verify(ROOT / "bubbles")["ok"])

    def test_rebuild_matches_committed_pixels(self):
        rebuilt = BUILD.build_atlas(ROOT / "source/rows", ROOT / "source/look-directions")
        committed = Image.open(ROOT / "bubbles/spritesheet.png").convert("RGBA")
        self.assertEqual(rebuilt.tobytes(), committed.tobytes())

    def test_mp4_build_uses_pinned_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary_dir = Path(tmp)
            packaged_ffmpeg = binary_dir / "ffmpeg-test-platform-v1"
            packaged_ffmpeg.touch()
            with (
                mock.patch.dict(os.environ, {"IMAGEIO_FFMPEG_EXE": "host-override"}),
                mock.patch.object(BUILD.resources, "files", return_value=binary_dir),
                mock.patch.object(BUILD.subprocess, "run") as run,
            ):
                BUILD.save_mp4(Path("input.gif"), Path("output.mp4"))

        command = run.call_args.args[0]
        self.assertEqual(command[0], str(packaged_ffmpeg))
        self.assertNotEqual(command[0], "host-override")
        self.assertTrue(run.call_args.kwargs["check"])

    def test_mp4_build_rejects_missing_packaged_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.dict(os.environ, {"IMAGEIO_FFMPEG_EXE": "host-override"}),
                mock.patch.object(BUILD.resources, "files", return_value=Path(tmp)),
                mock.patch.object(BUILD.subprocess, "run") as run,
                self.assertRaisesRegex(RuntimeError, "found 0"),
            ):
                BUILD.save_mp4(Path("input.gif"), Path("output.mp4"))

        run.assert_not_called()

    def test_video_comparison_rejects_different_decoded_frames(self):
        metadata = {"size": (16, 16), "fps": 10.0}
        black = b"\x00" * (16 * 16 * 3)
        white = b"\xff" * (16 * 16 * 3)

        def reader(frames):
            yield metadata
            yield from frames

        with (
            mock.patch.object(
                REPRO.imageio_ffmpeg,
                "read_frames",
                side_effect=[reader([black, white]), reader([white, black])],
            ),
            mock.patch.object(
                REPRO.imageio_ffmpeg,
                "count_frames_and_secs",
                side_effect=[(2, 0.2), (2, 0.2)],
            ),
        ):
            with self.assertRaisesRegex(SystemExit, "decoded frame 0 differs"):
                REPRO.compare_video(Path("committed.mp4"), Path("rebuilt.mp4"))

    def test_video_comparison_allows_bounded_encoder_noise(self):
        properties = {"size": [16, 16], "fps": 10.0, "frames": 1, "duration": 0.1}
        committed = b"\x64" * (16 * 16 * 3)
        rebuilt = b"\x65" * (16 * 16 * 3)
        with mock.patch.object(
            REPRO,
            "probe_video",
            side_effect=[(properties, [committed]), (properties, [rebuilt])],
        ):
            REPRO.compare_video(Path("committed.mp4"), Path("rebuilt.mp4"))

    def test_missing_required_frame_is_rejected(self):
        def mutate(atlas):
            draw = ImageDraw.Draw(atlas)
            draw.rectangle((0, 0, 191, 207), fill=(0, 0, 0, 0))
        self.assert_atlas_rejected(mutate)

    def test_unused_artwork_is_rejected(self):
        def mutate(atlas):
            draw = ImageDraw.Draw(atlas)
            draw.ellipse((6 * 192 + 70, 70, 6 * 192 + 90, 90), fill=(255, 0, 0, 255))
        self.assert_atlas_rejected(mutate)

    def test_visible_green_debris_is_rejected(self):
        def mutate(atlas):
            ImageDraw.Draw(atlas).rectangle((10, 10, 25, 25), fill=(0, 255, 0, 255))
        self.assert_atlas_rejected(mutate)

    def test_identical_look_directions_are_rejected(self):
        def mutate(atlas):
            first = atlas.crop((0, 9 * 208, 192, 10 * 208))
            for index in range(16):
                row, column = 9 + index // 8, index % 8
                atlas.paste(first, (column * 192, row * 208))
        self.assert_atlas_rejected(mutate)

    def test_fake_jump_row_is_rejected(self):
        def mutate(atlas):
            idle_a = atlas.crop((0, 0, 192, 208))
            idle_b = atlas.crop((192, 0, 384, 208))
            for column in range(5):
                atlas.paste(idle_a if column % 2 == 0 else idle_b, (column * 192, 4 * 208))
        self.assert_atlas_rejected(mutate)

    def test_metadata_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            shutil.copy2(ROOT / "bubbles/spritesheet.png", package / "spritesheet.png")
            metadata = json.loads((ROOT / "bubbles/pet.json").read_text())
            metadata["displayName"] = "Unexpected"
            (package / "pet.json").write_text(json.dumps(metadata))
            with self.assertRaises(SystemExit):
                VERIFY.verify(package)

    def test_committed_qa_attests_current_atlas(self):
        subprocess.run(["python3", str(ROOT / "scripts/check_qa_evidence.py")], check=True)

    def test_installer_keeps_unique_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "pets/bubbles"
            command = [str(ROOT / "scripts/install_bubbles_pet.sh"), str(ROOT / "bubbles"), str(target)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            (target / "marker").write_text("old")
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run(command, check=True, capture_output=True, text=True)
            backups = sorted(target.parent.glob("bubbles.backup.*"))
            self.assertEqual(len(backups), 2)
            self.assertTrue(any((backup / "marker").exists() for backup in backups))

    def test_installer_restores_previous_pet_when_final_swap_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            target = temp / "pets/bubbles"
            command = [str(ROOT / "scripts/install_bubbles_pet.sh"), str(ROOT / "bubbles"), str(target)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            (target / "marker").write_text("previous")

            wrapper_dir = temp / "bin"
            wrapper_dir.mkdir()
            counter = temp / "mv-count"
            wrapper = wrapper_dir / "mv"
            wrapper.write_text(
                "#!/usr/bin/env bash\n"
                f"counter={str(counter)!r}\n"
                "count=0\n"
                "[[ ! -f \"$counter\" ]] || count=$(<\"$counter\")\n"
                "count=$((count + 1))\n"
                "printf '%s' \"$count\" > \"$counter\"\n"
                "[[ $count -ne 2 ]] || exit 73\n"
                "exec /bin/mv \"$@\"\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{wrapper_dir}:{env['PATH']}"
            failed = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual((target / "marker").read_text(), "previous")


if __name__ == "__main__":
    unittest.main()
