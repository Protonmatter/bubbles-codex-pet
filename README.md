# Bubbles Codex Pet

Bubbles is a custom ChatGPT/Codex pet based on the real Bubbles: a small,
fluffy white dog with dark eyes, a black button nose, a pink heart collar, and
a tailored red waistcoat.

The repository follows the same engineering fundamentals as Pebble Poses:
state-specific source frames, deterministic assembly, strict validation,
reproducible previews, adversarial tests, pinned CI actions, and traceable
asset provenance.

![Bubbles animation preview](preview/bubbles-animation-preview.gif)

## Runtime package

```text
bubbles/
├── pet.json
└── spritesheet.png
```

The runtime atlas uses the Codex v2 contract:

- 1536 × 2288 pixels
- 8 × 11 cells
- 192 × 208 pixels per cell
- transparent unused cells
- 73 required frames: 57 activity frames and 16 look directions

## Animation contract

| Row | State | Frames |
|---:|---|---:|
| 0 | idle | 6 |
| 1 | running-right | 8 |
| 2 | running-left | 8 |
| 3 | waving | 4 |
| 4 | jumping | 5 |
| 5 | failed | 8 |
| 6 | waiting | 6 |
| 7 | running | 6 |
| 8 | review | 6 |
| 9–10 | 16-direction look loop | 16 |

The look loop advances clockwise from `000 up` through `090 right`, `180
down`, `270 left`, and back toward up in 22.5° increments.

## Build and verify

```bash
python3 -m pip install --require-hashes --requirement requirements.txt
python3 scripts/build_bubbles_pet.py
python3 scripts/verify_bubbles_pet.py bubbles
python3 -m unittest discover --start-directory tests --verbose
```

The build is assembled only from the approved 192×208 source cells in
`source/rows/` and `source/look-directions/`. It also regenerates every GIF,
both MP4 previews, the contact sheet, and a timing manifest from the encoded
atlas. CI compares runtime metadata, decoded PNG/WebP pixels, GIF frames and
timing, and decoded MP4 frame content and stream properties with a fresh
rebuild. MP4 content checks use bounded whole-frame and 16-pixel-block error
limits so platform encoder differences cannot hide reordered or altered
frames. Preview encoding uses only the FFmpeg executable packaged by the pinned
`imageio-ffmpeg` dependency; environment, Conda, `PATH`, and system overrides
are not accepted.

## Install locally

```bash
./scripts/install_bubbles_pet.sh
```

The installer targets `${CODEX_HOME:-$HOME/.codex}/pets/bubbles`, verifies and
stages the new package beside the destination, then atomically swaps it into
place. Existing installations receive collision-resistant backups, and a
failed final swap restores the previous pet.

## QA evidence

- [Full contact sheet](preview/bubbles-contact-sheet.png)
- [Look-direction loop](preview/bubbles-look-loop.gif)
- [Atlas validation](docs/validation.json)
- [Quality gate](docs/quality-gate.json)
- [Independent direction check](docs/direction-blind-validation.json)
- [Asset provenance](docs/ASSET-PROVENANCE.md)

The final v2 atlas also passed the authenticated ChatGPT Pets preflight with
the required frame counts `[6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]`.
