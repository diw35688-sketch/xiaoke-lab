from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Validate 72-direction eye overlay frames.')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--frames-dir', type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    expected_size = (manifest['canvas']['width'], manifest['canvas']['height'])
    eye_box = tuple(manifest['eye_box'])
    failures: list[str] = []
    bboxes: dict[str, tuple[int, int, int, int] | None] = {}

    for name in manifest['frames']:
        path = args.frames_dir / name
        if not path.exists():
            failures.append(f'MISSING {name}')
            continue

        try:
            image = Image.open(path)
            image.load()
        except Exception as exc:
            failures.append(f'UNREADABLE {name}: {exc}')
            continue

        if image.size != expected_size:
            failures.append(f'SIZE {name}: {image.size}, expected {expected_size}')
        if image.mode != 'RGBA':
            failures.append(f'MODE {name}: {image.mode}, expected RGBA')
            image = image.convert('RGBA')

        alpha = image.getchannel('A')
        bbox = alpha.getbbox()
        bboxes[name] = bbox
        if bbox is None:
            failures.append(f'EMPTY_ALPHA {name}')
            continue

        corners = [alpha.getpixel((0, 0)), alpha.getpixel((image.width - 1, 0)), alpha.getpixel((0, image.height - 1)), alpha.getpixel((image.width - 1, image.height - 1))]
        if any(corners):
            failures.append(f'OPAQUE_CORNER {name}: {corners}')

        outside = alpha.copy()
        inside = alpha.crop(eye_box)
        outside.paste(0, eye_box)
        if outside.getbbox() is not None:
            failures.append(f'ALPHA_OUTSIDE_EYE_BOX {name}: bbox={outside.getbbox()}')
        if inside.getbbox() is None:
            failures.append(f'NO_ALPHA_INSIDE_EYE_BOX {name}')

    print(f"validated={len(bboxes)}/{len(manifest['frames'])}, failures={len(failures)}")
    for failure in failures:
        print(failure)
    if bboxes:
        unique = sorted({bbox for bbox in bboxes.values() if bbox is not None})
        print(f'unique_alpha_bboxes={len(unique)}')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
