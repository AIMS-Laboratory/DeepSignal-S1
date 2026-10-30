"""Copy verified clean-view recordings under public names and build GIF previews."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import imageio_ffmpeg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path, default=ROOT / '.local/media-preview-sources')
    args = parser.parse_args()
    original = json.loads((ROOT / 'assets/previews/manifest.json').read_text())['files']
    output = ROOT / 'assets/videos'
    output.mkdir(exist_ok=True)
    records = {}
    for language in ('en', 'zh'):
        for scene, public_name in (('nansha', 'multi-intersection'), ('town', 'standard-simulation')):
            key = f'{language}/{scene}-clean.mp4'
            source = args.source_dir / key
            expected = original[key]['source_sha256']
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise ValueError(f'Source does not match the published recording: {key}')
            stem = f's1-{public_name}-clean-{language}'
            video = output / f'{stem}.mp4'
            shutil.copyfile(source, video)
            preview = output / f'{stem}.gif'
            filters = ('fps=8,scale=800:-1:flags=lanczos,split[a][b];'
                       '[a]palettegen=max_colors=96:stats_mode=diff[p];'
                       '[b][p]paletteuse=dither=bayer:bayer_scale=3')
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(source),
                            '-filter_complex', filters, '-loop', '0', '-y', str(preview)], check=True)
            with Image.open(preview) as im:
                duration = sum((im.seek(i) or im.info.get('duration', 0)) for i in range(im.n_frames))
                assert im.n_frames > 1 and duration >= 11900
                assert preview.stat().st_size < 4_800_000
            records[key] = dict(video=str(video.relative_to(ROOT)), source=original[key]['source'],
                                sha256=expected, preview=str(preview.relative_to(ROOT)),
                                preview_sha256=hashlib.sha256(preview.read_bytes()).hexdigest(),
                                duration_ms=duration)
            print(stem, flush=True)
    (output / 'manifest.json').write_text(json.dumps({
        'method': 'MP4 bytes unchanged. Full published window at original 5x speed; 800px, 8fps GIF; no synthesized frames.',
        'files': records}, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
