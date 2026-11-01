"""Builds the video: for every scene it draws a background + a text layer
(Pillow), makes a voiceover (edge-tts), animates it with ffmpeg (slow zoom,
text slide-in + fade) and joins everything, optionally with background music."""
import asyncio
import random
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

W, H, FPS = config.WIDTH, config.HEIGHT, config.FPS
BOLD = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
REG = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
       "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(size, bold=True):
    for p in (BOLD if bold else REG):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ---------- stills ----------

def background(pal, visual_path, seed):
    c1, c2 = rgb(pal["bg1"]), rgb(pal["bg2"])
    g = Image.linear_gradient("L")
    mask = Image.blend(g.resize((W, H)), g.rotate(90).resize((W, H)), 0.5)
    base = Image.composite(Image.new("RGB", (W, H), c2), Image.new("RGB", (W, H), c1), mask).convert("RGBA")
    rnd = random.Random(seed)
    glow = Image.new("RGBA", (480, 270), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for _ in range(2):
        x, y, r = rnd.randint(40, 440), rnd.randint(20, 250), rnd.randint(50, 90)
        gd.ellipse((x - r, y - r, x + r, y + r), fill=rgb(pal["accent"]) + (110,))
    glow = glow.filter(ImageFilter.GaussianBlur(28)).resize((W, H), Image.BICUBIC)
    base = Image.alpha_composite(base, glow)
    if visual_path:
        box_w, box_h, x0, y0 = 900, 620, 930, (H - 620) // 2
        im = Image.open(visual_path).convert("RGB")
        scale = max(box_w / im.width, box_h / im.height)
        im = im.resize((int(im.width * scale) + 1, int(im.height * scale) + 1), Image.LANCZOS)
        left, top = (im.width - box_w) // 2, 0
        im = im.crop((left, top, left + box_w, top + box_h))
        m = Image.new("L", (box_w, box_h), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, box_w, box_h), 36, fill=255)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + 24, x0 + box_w, y0 + box_h + 24), 36, fill=(0, 0, 0, 150))
        base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(30)))
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(frame).rounded_rectangle((x0 - 4, y0 - 4, x0 + box_w + 4, y0 + box_h + 4), 40,
                                                outline=rgb(pal["accent"]) + (255,), width=4)
        base = Image.alpha_composite(base, frame)
        base.paste(im, (x0, y0), m)
    return base.convert("RGB")


def text_layer(scene, pal, site, logo_path, has_visual):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    center = not has_visual
    max_w = 1500 if center else 760
    x_left = 110
    head, sub = scene["headline"], scene.get("subtext", "")
    size = 100
    while size > 52:
        f = font(size)
        lines = wrap(d, head, f, max_w)
        if len(lines) <= (3 if center else 4):
            break
        size -= 6
    f = font(size)
    lines = wrap(d, head, f, max_w)
    sf = font(40, bold=False)
    sub_lines = wrap(d, sub, sf, max_w) if sub else []
    lh, sh = int(size * 1.15), 54
    total = len(lines) * lh + 36 + len(sub_lines) * sh
    y = (H - total) // 2
    for ln in lines:
        w = d.textlength(ln, font=f)
        x = (W - w) / 2 if center else x_left
        d.text((x + 3, y + 4), ln, font=f, fill=(0, 0, 0, 110))
        d.text((x, y), ln, font=f, fill=rgb(pal["text"]) + (255,))
        y += lh
    y += 12
    bar_w = 120
    bx = (W - bar_w) / 2 if center else x_left
    d.rounded_rectangle((bx, y, bx + bar_w, y + 8), 4, fill=rgb(pal["accent"]) + (255,))
    y += 24
    for ln in sub_lines:
        w = d.textlength(ln, font=sf)
        x = (W - w) / 2 if center else x_left
        d.text((x, y), ln, font=sf, fill=rgb(pal["muted"]) + (255,))
        y += sh
    # brand tag, top-left
    bx0 = 80
    if logo_path:
        lg = Image.open(logo_path).convert("RGBA")
        lg.thumbnail((90, 90))
        img.alpha_composite(lg, (bx0, 60))
        bx0 += lg.width + 20
    d.text((bx0, 78), site["name"], font=font(38), fill=rgb(pal["text"]) + (230,))
    if scene["role"] == "cta" and site["host"].lower() not in head.lower():
        pill = site["host"]
        pf = font(48)
        pw = d.textlength(pill, font=pf) + 90
        px, py = (W - pw) / 2, H - 230
        d.rounded_rectangle((px, py, px + pw, py + 90), 45, fill=rgb(pal["accent"]) + (255,))
        d.text((px + 45, py + 16), pill, font=pf, fill=(10, 10, 20, 255))
    return img


# ---------- audio ----------

def make_voice(text, path, voice):
    if not text.strip():
        return False
    try:
        import edge_tts

        async def go():
            await edge_tts.Communicate(text, voice).save(str(path))
        asyncio.run(go())
        return path.exists() and path.stat().st_size > 1000
    except Exception:
        path.unlink(missing_ok=True)
        return False


def duration_of(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + r.stderr[-600:])


# ---------- main ----------

def render_video(site, storyboard, work_dir, out_path, voice, progress=print):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found. Install it:  winget install Gyan.FFmpeg  (then reopen the terminal)")
    work_dir = Path(work_dir)
    pal = site["palette"]
    logo = work_dir / site["logo"] if site.get("logo") else None
    scenes = storyboard["scenes"]
    clips = []
    for i, sc in enumerate(scenes):
        progress(f"Scene {i + 1} of {len(scenes)}: preparing…")
        vis = sc.get("visual")
        vpath = work_dir / vis["file"] if vis and (work_dir / vis["file"]).exists() else None
        background(pal, vpath, i).save(work_dir / f"bg_{i}.png")
        text_layer(sc, pal, site, logo, bool(vpath)).save(work_dir / f"tx_{i}.png")
        narr = work_dir / f"narr_{i}.mp3"
        has_voice = make_voice(sc.get("narration", ""), narr, voice)
        if has_voice:
            dur = (duration_of(narr) or 3.0) + 1.0
        else:
            words = len(sc.get("narration", "").split()) or 6
            dur = words / 2.5 + 1.0
        dur = round(max(3.5, dur), 2)
        zoom = ("min(1+0.0006*on,1.13)" if i % 2 == 0 else "max(1.13-0.0006*on,1)")
        fc = (f"[0:v]scale=2400:1350,zoompan=z='{zoom}':d=1:x='iw/2-(iw/zoom/2)':"
              f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}[bg];"
              f"[1:v]format=rgba,fade=t=in:st=0.3:d=0.7:alpha=1[tx];"
              f"[bg][tx]overlay=x=0:y='46*pow(max(0,1-t/0.9),2)':format=auto,"
              f"fade=t=in:st=0:d=0.35,fade=t=out:st={dur - 0.4}:d=0.4,format=yuv420p[v]")
        cmd = ["ffmpeg", "-y", "-loop", "1", "-t", str(dur), "-i", f"bg_{i}.png",
               "-loop", "1", "-t", str(dur), "-i", f"tx_{i}.png"]
        if has_voice:
            cmd += ["-i", narr.name]
            fc += f";[2:a]adelay=450|450,apad=whole_dur={dur},aformat=sample_rates=44100:channel_layouts=stereo[a]"
        else:
            cmd += ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=44100:cl=stereo"]
            fc += ";[2:a]anull[a]"
        out = f"clip_{i}.mp4"
        cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", str(dur), "-r", str(FPS),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-ar", "44100",
                "-ac", "2", out]
        progress(f"Scene {i + 1} of {len(scenes)}: animating…")
        run(cmd, work_dir)
        clips.append(out)
    progress("Joining scenes…")
    (work_dir / "list.txt").write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    joined = "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", joined], work_dir)
    music = next((p for p in sorted(config.MUSIC.glob("*")) if p.suffix.lower() in (".mp3", ".wav", ".m4a")), None)
    final = Path(out_path)
    if music:
        progress("Adding music…")
        run(["ffmpeg", "-y", "-i", joined, "-stream_loop", "-1", "-i", str(music), "-filter_complex",
             "[0:a]volume=1.5[v];[1:a]volume=0.18[m];[v][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)], work_dir)
    else:
        shutil.copy(work_dir / joined, final)
    return final
