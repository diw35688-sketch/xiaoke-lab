from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Prepare references for a 72-direction avatar eye sequence.')
    parser.add_argument('--master', type=Path, required=True, help='RGBA assistant master portrait')
    parser.add_argument('--out-dir', type=Path, required=True, help='Generation-pack output directory')
    parser.add_argument('--eye-box', type=int, nargs=4, default=(420, 340, 780, 550), metavar=('L', 'T', 'R', 'B'))
    return parser.parse_args()


def draw_target(path: Path, angle: int | None) -> None:
    size = 512
    center = size // 2
    radius = 170
    image = Image.new('RGB', (size, size), '#f2f4f8')
    draw = ImageDraw.Draw(image)
    draw.line((center - 210, center, center + 210, center), fill='#687386', width=3)
    draw.line((center, center - 210, center, center + 210), fill='#687386', width=3)

    if angle is None:
        tx = ty = center
        label = 'GAZE TARGET CENTER'
    else:
        radians = math.radians(angle)
        tx = center + radius * math.cos(radians)
        ty = center + radius * math.sin(radians)
        draw.line((center, center, tx, ty), fill='#94a3b8', width=4)
        label = f'GAZE TARGET {angle:03d} deg'

    draw.ellipse((tx - 18, ty - 18, tx + 18, ty + 18), fill='#ef233c', outline='#7f1d1d', width=4)
    draw.text((18, 16), label, fill='#111827')
    draw.text((18, 42), 'screen coordinates: 000=right, 090=down', fill='#334155')
    image.save(path)


def main() -> int:
    args = parse_args()
    master_path = args.master.resolve()
    out_dir = args.out_dir.resolve()
    references = out_dir / 'references'
    targets = references / 'gaze_targets'
    prompts = out_dir / 'prompts'
    for directory in (references, targets, prompts):
        directory.mkdir(parents=True, exist_ok=True)

    master = Image.open(master_path).convert('RGBA')
    eye_box = tuple(args.eye_box)
    if not (0 <= eye_box[0] < eye_box[2] <= master.width and 0 <= eye_box[1] < eye_box[3] <= master.height):
        raise ValueError(f'eye box {eye_box} is outside master canvas {master.size}')

    shutil.copy2(master_path, references / 'assistant_master.png')
    master.crop(eye_box).save(references / 'assistant_eyes_identity.png')
    draw_target(targets / 'target_center.png', None)
    for angle in range(0, 360, 5):
        draw_target(targets / f'target_{angle:03d}.png', angle)

    frames = ['look_center.png', *[f'look_{angle:03d}.png' for angle in range(0, 360, 5)]]
    anchors = ['look_center.png', *[f'look_{angle:03d}.png' for angle in range(0, 360, 45)]]
    manifest = {
        'canvas': {'width': master.width, 'height': master.height},
        'eye_box': list(eye_box),
        'frame_count': len(frames),
        'direction_count': 72,
        'step_degrees': 5,
        'coordinate_convention': 'screen coordinates; 000=right, 090=down, 180=left, 270=up',
        'frames': frames,
        'anchors': anchors,
    }
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Prepared {len(frames)} frame references in {out_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
