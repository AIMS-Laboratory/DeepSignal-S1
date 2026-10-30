"""Rebuild public previews from existing GitHub attachments (Pillow + imageio-ffmpeg)."""
import concurrent.futures, hashlib, json, subprocess
from pathlib import Path
import imageio_ffmpeg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.local' / 'media-preview-sources'
CACHE.mkdir(parents=True, exist_ok=True)
OUT = ROOT / 'assets/previews'
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
videos = json.loads((ROOT/'results/fusion-2026-10-30-github-videos.json').read_text())['videos']

def build(item):
    key, url = item
    src = CACHE / key
    src.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        subprocess.run(['curl','-fsSL','--retry','2','--retry-all-errors','--max-time','60',url,'-o',str(src)],check=True)
    dest = OUT / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG,'-v','error','-i',str(src),'-frames:v','1','-q:v','3','-y',str(dest.with_suffix('.jpg'))],check=True)
    record = dict(source=url, source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(), poster=str(dest.with_suffix('.jpg').relative_to(ROOT)))
    if '-clean' not in key:
        gif = dest.with_suffix('.gif')
        shake = '-shake5' in key
        filt=('fps=6,scale=640:-1:flags=lanczos' if shake else 'fps=8,scale=800:-1:flags=lanczos') + ',split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3'
        trim = ['-ss','3.6','-t','4.8'] if shake else []
        subprocess.run([FFMPEG,'-v','error','-i',str(src),*trim,'-filter_complex',filt,'-loop','0','-y',str(gif)],check=True)
        record['clip_start_s'] = 3.6 if shake else 0
        im=Image.open(gif)
        duration=sum((im.seek(i) or im.info.get('duration',0)) for i in range(im.n_frames))
        record.update(preview=str(gif.relative_to(ROOT)), bytes=gif.stat().st_size, frames=im.n_frames, duration_ms=duration, size=list(im.size), sha256=hashlib.sha256(gif.read_bytes()).hexdigest())
        assert im.n_frames > 1 and gif.stat().st_size < 4_800_000, record
    print(key, record.get('bytes','poster only'), flush=True)
    return key,record

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    records=dict(pool.map(build,videos.items()))
(OUT/'manifest.json').write_text(json.dumps({'source_manifest':'results/fusion-2026-10-30-github-videos.json','method':'Published GitHub clips at original 5x playback. Non-shake: full clip, 800px, 8fps. Shake: central 4.8s (24 simulation seconds), 640px, 6fps. 96-color GIF; first-frame JPEG. No synthesized frames; full published video links retained.','files':records},ensure_ascii=False,indent=2)+'\n')
