#!/usr/bin/env python3
"""ASZ Reels Studio v2 — footage-led reel renderer.

  python3 studio/render_v2.py --edit studio/edit-<slug>.json --out reels/<slug>.mp4 \
          --cover covers/<slug>.jpg --check-dir /tmp/chk

Each shot in the edit plan is filled from <footageDir>/<id>.(mp4|mov|jpg|jpeg|png).
A missing shot becomes a labelled FOOTAGE NEEDED slate and the whole render is
marked PREVIEW (report.preview = true) — a preview is never published.
Logo: original file, top-left on a small white card; large on the end card only.
Captions: one short line per shot, words rise in one after another.
"""
import argparse, json, math, os, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GF = "/usr/share/fonts/truetype/google-fonts"
def F(w, s): return ImageFont.truetype(f"{GF}/Poppins-{w}.ttf", s)

SAFFRON = (255, 176, 32)
NAVY = (12, 20, 38)

def ease_out(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def run(cmd): subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def find_media(d, sid):
    for ext in ("mp4", "mov", "MP4", "MOV", "jpg", "jpeg", "png", "JPG", "PNG"):
        p = os.path.join(d, f"{sid}.{ext}")
        if os.path.exists(p): return p
    return None

def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w or not cur: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

# ---------- static pieces ----------
def logo_card(logo, width, pad, radius, shadow=True):
    lw = width - 2 * pad
    lg = logo.resize((lw, round(logo.height * lw / logo.width)), Image.LANCZOS)
    h = lg.height + 2 * pad
    S = 24 if shadow else 0
    card = Image.new("RGBA", (width + 2 * S, h + 2 * S), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((S, S + 6, S + width, S + h + 6), radius, fill=(0, 0, 0, 110))
        card = Image.alpha_composite(card, sh.filter(ImageFilter.GaussianBlur(12)))
    body = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(body).rounded_rectangle((S, S, S + width, S + h), radius, fill=(255, 255, 255, 250))
    card = Image.alpha_composite(card, body)
    card.paste(lg, (S + pad, S + pad))
    return card, S

def slate(shot, W, H):
    im = Image.new("RGB", (W, H), (26, 29, 36))
    d = ImageDraw.Draw(im)
    for x in range(-H, W, 60): d.line((x, 0, x + H, H), fill=(32, 35, 43), width=18)
    d.rounded_rectangle((90, 520, W - 90, 1080), 28, outline=(255, 176, 32), width=4, fill=(20, 22, 28))
    d.text((W / 2, 600), "FOOTAGE NEEDED", font=F("Bold", 54), fill=SAFFRON, anchor="mm")
    d.text((W / 2, 680), f"{shot['id'].upper()}  ·  {shot['type']}  ·  {shot['end'] - shot['start']:.1f} s",
           font=F("Medium", 36), fill=(230, 230, 230), anchor="mm")
    f = F("Regular", 33); y = 750
    for ln in wrap(d, shot["need"], f, W - 260):
        d.text((W / 2, y), ln, font=f, fill=(200, 204, 212), anchor="mm"); y += 46
    return im

def end_bg(W, H):
    y = np.linspace(0, 1, H)[:, None]; x = np.linspace(-1, 1, W)[None, :]
    base = np.zeros((H, W, 3), np.float32)
    for c in range(3): base[..., c] = NAVY[c] * (1 - 0.35 * y) + 0 * x
    glow = np.exp(-((x * 1.1) ** 2 + ((y - 0.38) * 2.6) ** 2))[..., None] * np.array([150, 70, 20], np.float32) * 0.55
    return Image.fromarray(np.clip(base + glow, 0, 255).astype(np.uint8)).convert("RGBA")

# ---------- animated caption ----------
def draw_words(frame, lines, font, cx, top, t_in, t, color_for, line_gap=1.22, stagger=0.07, dur=0.38, alpha_mul=1.0):
    """Words rise 34 px and fade in, one after another. Returns the text box drawn."""
    d = ImageDraw.Draw(frame)
    asc = font.size * line_gap
    k = 0
    for li, ln in enumerate(lines):
        words = ln.split()
        space = d.textlength(" ", font=font)
        total = sum(d.textlength(w, font=font) for w in words) + space * (len(words) - 1)
        x = cx - total / 2
        for w in words:
            p = ease_out((t - t_in - k * stagger) / dur)
            if p > 0:
                a = int(255 * p * alpha_mul)
                layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                ld = ImageDraw.Draw(layer)
                yy = top + li * asc + (1 - p) * 34
                ld.text((x + 2, yy + 3), w, font=font, fill=(0, 0, 0, int(a * 0.55)))
                ld.text((x, yy), w, font=font, fill=color_for(li) + (a,))
                frame.alpha_composite(layer)
            x += d.textlength(w, font=font) + space
            k += 1
    return k

class Overlay:
    def __init__(self, edit, W, H, preview, logo):
        self.e, self.W, self.H, self.preview = edit, W, H, preview
        self.small, self.sS = logo_card(logo, 320, 16, 18)
        self.big, self.bS = logo_card(logo, 640, 30, 30)
        self.endbg = end_bg(W, H)
        self.fcap = F("Bold", 62); self.fhook = F("Bold", 64)
        self.fend = F("Bold", 58); self.furl = F("Medium", 40); self.fcta = F("Regular", 32)
        self.ftag = F("Medium", 26)
        self.scratch = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    def caption_box(self, frame, lines, font, t_in, t, t_out):
        d = self.scratch
        asc = font.size * 1.22
        w = max(d.textlength(l, font=font) for l in lines) + 72
        h = asc * len(lines) + 40
        cy = 1290
        top = cy - h / 2
        p = ease_out((t - t_in) / 0.28)
        fade = 1.0 - ease_out((t - (t_out - 0.2)) / 0.2) if t > t_out - 0.2 else 1.0
        if p <= 0: return top, 0.0
        bw = w * (0.86 + 0.14 * p)
        box = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle(
            (self.W / 2 - bw / 2, top, self.W / 2 + bw / 2, top + h), 26,
            fill=(10, 12, 18, int(150 * p * fade)))
        frame.alpha_composite(box)
        # saffron accent bar grows from the left edge
        acc = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        ImageDraw.Draw(acc).rounded_rectangle(
            (self.W / 2 - bw / 2, top + 14, self.W / 2 - bw / 2 + 7, top + 14 + (h - 28) * p), 3,
            fill=SAFFRON + (int(255 * fade),))
        frame.alpha_composite(acc)
        return top + 20, fade

    def frame(self, t):
        fr = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        ec = self.e["endCard"]
        if t >= ec["start"]:
            return self.end_frame(fr, t - ec["start"], ec)
        # logo, top-left: slides in from the left in the first half-second
        p = ease_out(t / 0.5)
        lx = int(44 - (1 - p) * 60) - self.sS; ly = 92 - self.sS
        lay = Image.new("RGBA", fr.size, (0, 0, 0, 0)); lay.alpha_composite(self.small, (max(lx, -self.sS - 400), ly))
        if p < 1: lay.putalpha(lay.getchannel("A").point(lambda v: int(v * p)))
        fr.alpha_composite(lay)
        for sh in self.e["shots"]:
            if sh["start"] <= t < sh["end"]:
                self.shot_caption(fr, sh, t)
        if self.preview:
            ImageDraw.Draw(fr).rounded_rectangle((700, 100, 1036, 150), 12, fill=(200, 30, 30, 220))
            ImageDraw.Draw(fr).text((868, 125), "PREVIEW · footage pending", font=self.ftag, fill="white", anchor="mm")
        return fr

    def shot_caption(self, fr, sh, t):
        d = self.scratch
        if sh.get("hook"):
            l1 = wrap(d, sh["caption"][0], self.fhook, 960)
            l2 = wrap(d, sh["caption"][1], self.fhook, 960)
            lines = l1 + l2
            top, fade = self.caption_box(fr, lines, self.fhook, sh["start"] + 0.05, t, sh["end"])
            n1 = len(l1)
            draw_words(fr, l1, self.fhook, self.W / 2, top, sh["start"] + 0.12, t, lambda i: (255, 255, 255), alpha_mul=fade)
            lay = Image.new("RGBA", fr.size, (0, 0, 0, 0))
            draw_words(lay, [""] * n1 + l2, self.fhook, self.W / 2, top, sh["start"] + 1.05, t, lambda i: SAFFRON, alpha_mul=fade)
            fr.alpha_composite(lay)
            return
        lines = wrap(d, sh["caption"][0], self.fcap, 860)
        top, fade = self.caption_box(fr, lines, self.fcap, sh["start"] + 0.08, t, sh["end"])
        draw_words(fr, lines, self.fcap, self.W / 2, top, sh["start"] + 0.14, t,
                   lambda i: (255, 255, 255), alpha_mul=fade)

    def end_frame(self, fr, u, ec):
        a = ease_out(u / 0.35)
        bg = self.endbg.copy(); bg.putalpha(int(255 * a)); fr.alpha_composite(bg)
        # big logo: settles from 94% to 100% scale
        p = ease_out((u - 0.1) / 0.5)
        if p > 0:
            s = 0.94 + 0.06 * p
            lg = self.big.resize((int(self.big.width * s), int(self.big.height * s)), Image.LANCZOS)
            lg.putalpha(lg.getchannel("A").point(lambda v: int(v * p)))
            fr.alpha_composite(lg, (int(self.W / 2 - lg.width / 2), int(640 - lg.height / 2)))
        lines = wrap(self.scratch, ec["headline"], self.fend, 900)
        draw_words(fr, lines, self.fend, self.W / 2, 900, 0.45, u, lambda i: (255, 255, 255))
        q = ease_out((u - 1.1) / 0.4)
        if q > 0:
            uw = self.scratch.textlength(ec["url"], font=self.furl) + 80
            y = 1110 + (1 - q) * 24
            pill = Image.new("RGBA", fr.size, (0, 0, 0, 0)); pd = ImageDraw.Draw(pill)
            pd.rounded_rectangle((self.W / 2 - uw / 2, y, self.W / 2 + uw / 2, y + 76), 38, fill=SAFFRON + (int(255 * q),))
            pd.text((self.W / 2, y + 38), ec["url"], font=self.furl, fill=(20, 20, 20, int(255 * q)), anchor="mm")
            pd.text((self.W / 2, y + 140), ec["cta"], font=self.fcta, fill=(225, 225, 230, int(255 * q)), anchor="mm")
            fr.alpha_composite(pill)
        return fr

# ---------- audio ----------
def music_bed(path, dur, sr=44100):
    """Quiet warm pad (synthesised here, no licensed track): Am-F-C-G, soft sines, slow swells."""
    t = np.arange(int(dur * sr)) / sr
    chords = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [196.0, 261.63, 329.63], [196.0, 246.94, 293.66]]
    out = np.zeros_like(t)
    seg = 3.5
    for i in range(int(math.ceil(dur / seg)) + 1):
        c = chords[i % 4]; t0 = i * seg
        env = np.clip((t - t0) / 1.2, 0, 1) * np.clip((t0 + seg + 1.2 - t) / 1.2, 0, 1)
        for f in c:
            for det in (-0.6, 0.6):
                out += env * np.sin(2 * np.pi * (f + det) * t) * 0.05
            out += env * np.sin(2 * np.pi * f / 2 * t) * 0.03
    out *= np.clip(t / 1.0, 0, 1) * np.clip((dur - t) / 1.5, 0, 1)
    pcm = (out / max(1e-9, np.abs(out).max()) * 0.5 * 32767).astype(np.int16)
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--cover", required=True); ap.add_argument("--check-dir", required=True)
    a = ap.parse_args()
    e = json.load(open(a.edit)); W, H, FPS = e["width"], e["height"], e["fps"]
    fdir = os.path.join(ROOT, e["footageDir"]); voice = os.path.join(ROOT, e["voice"])
    total = e["endCard"]["end"]
    tmp = tempfile.mkdtemp(prefix="aszv2-")
    os.makedirs(a.check_dir, exist_ok=True)
    missing, segs = [], []
    # 1) base: one segment per shot (real clip, still photo, or slate), then the end-card bed
    for sh in e["shots"]:
        d = sh["end"] - sh["start"]; src = find_media(fdir, sh["id"]); seg = os.path.join(tmp, f"{sh['id']}.mp4")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
              "eq=contrast=1.04:saturation=1.06,format=yuv420p")
        if src and src.lower().endswith((".mp4", ".mov")):
            run(["ffmpeg", "-y", "-ss", str(sh.get("in", 0.4)), "-t", f"{d:.3f}", "-i", src,
                 "-f", "lavfi", "-t", f"{d:.3f}", "-i", "anullsrc=r=44100:cl=mono",
                 "-filter_complex", f"[0:v]{vf}[v];[0:a]aresample=44100,aformat=channel_layouts=mono[a0];[a0][1:a]amix=inputs=2:duration=longest[a]",
                 "-map", "[v]", "-map", "[a]", "-t", f"{d:.3f}", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", seg]) \
                if has_audio(src) else \
            run(["ffmpeg", "-y", "-ss", str(sh.get("in", 0.4)), "-t", f"{d:.3f}", "-i", src,
                 "-f", "lavfi", "-t", f"{d:.3f}", "-i", "anullsrc=r=44100:cl=mono",
                 "-map", "0:v", "-map", "1:a", "-vf", vf, "-t", f"{d:.3f}", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", seg])
        else:
            img = os.path.join(tmp, f"{sh['id']}.png")
            if src: Image.open(src).convert("RGB").save(img)
            else: slate(sh, W, H).save(img); missing.append(sh["id"])
            # a photo gets one gentle drift (not on every shot) — a slate stays still
            move = f",zoompan=z='1+0.03*on/{int(d*FPS)}':d={int(d*FPS)}:s={W}x{H}:fps={FPS}" if src else ""
            run(["ffmpeg", "-y", "-loop", "1", "-t", f"{d:.3f}", "-i", img,
                 "-f", "lavfi", "-t", f"{d:.3f}", "-i", "anullsrc=r=44100:cl=mono",
                 "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}{move},fps={FPS},format=yuv420p",
                 "-t", f"{d:.3f}", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", seg])
        segs.append(seg)
    ed = e["endCard"]["end"] - e["endCard"]["start"]; endseg = os.path.join(tmp, "end.mp4")
    last = find_media(fdir, e["shots"][-1]["id"])
    run(["ffmpeg", "-y", "-f", "lavfi", "-t", f"{ed:.3f}", "-i", f"color=c=0x0c1426:s={W}x{H}:r={FPS}",
         "-f", "lavfi", "-t", f"{ed:.3f}", "-i", "anullsrc=r=44100:cl=mono",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", endseg])
    segs.append(endseg)
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
    base = os.path.join(tmp, "base.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", base])
    preview = bool(missing) or not os.path.exists(voice)

    # 2) overlay frames (logo, moving captions, end card) piped as RGBA
    ov = Overlay(e, W, H, preview, Image.open(os.path.join(ROOT, e["logo"])).convert("RGB"))
    nfr = int(round(total * FPS))
    music = os.path.join(tmp, "music.wav"); music_bed(music, total)
    vo_in = ["-i", voice] if os.path.exists(voice) else []
    aud = e["audio"]
    if vo_in:
        af = (f"[0:a]volume={aud['locationDb']}dB[loc];"
              f"[3:a]loudnorm=I={aud['voiceLufs']}:TP=-1.5,adelay=150|150,asplit=2[vo][sc];"
              f"[2:a]loudnorm=I={aud['musicLufs']}[m0];[m0][sc]sidechaincompress=threshold=0.03:ratio=6:attack=40:release=400[m];"
              f"[loc][vo][m]amix=inputs=3:normalize=0,alimiter=limit=0.89[a]")
    else:
        af = (f"[0:a]volume={aud['locationDb']}dB[loc];[2:a]loudnorm=I={aud['musicLufs'] + 6}[m];"
              f"[loc][m]amix=inputs=2:normalize=0,alimiter=limit=0.89[a]")
    out = os.path.join(ROOT, a.out)
    cmd = ["ffmpeg", "-y", "-i", base, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", music] + vo_in + [
           "-filter_complex", f"[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v];{af}",
           "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-r", str(FPS),
           "-c:v", "libx264", "-profile:v", "high", "-crf", "21", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for i in range(nfr):
        p.stdin.write(ov.frame(i / FPS).tobytes())
    p.stdin.close(); err = p.stderr.read(); p.wait()
    if p.returncode: sys.stderr.write(err.decode()[-2000:]); sys.exit(1)

    # 3) cover + check frames
    run(["ffmpeg", "-y", "-ss", "1.9", "-i", out, "-frames:v", "1", "-q:v", "2", os.path.join(ROOT, a.cover)])
    checks = [1.0, 1.9] + [round((s["start"] + s["end"]) / 2, 2) for s in e["shots"][1:]] + [26.9]
    for tt in checks:
        run(["ffmpeg", "-y", "-ss", str(tt), "-i", out, "-frames:v", "1", "-vf", "scale=432:-1", os.path.join(a.check_dir, f"t{tt:05.2f}.jpg")])
    pr = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
                                             "-show_entries", "format=duration,size", "-of", "json", out]))
    loud = subprocess.run(["ffmpeg", "-i", out, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    il = [l for l in loud.splitlines() if l.strip().startswith("I:")]
    rep = {"out": a.out, "preview": preview, "missingShots": missing, "voice": os.path.exists(voice),
           "duration": float(pr["format"]["duration"]), "sizeMB": round(int(pr["format"]["size"]) / 1e6, 2),
           "streams": [s["codec_type"] + (f" {s['width']}x{s['height']}" if "width" in s else "") for s in pr["streams"]],
           "integratedLUFS": il[-1].split()[1] if il else None, "checkFrames": a.check_dir}
    print(json.dumps(rep, indent=2))
    shutil.rmtree(tmp, ignore_errors=True)

def has_audio(src):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", src],
                       capture_output=True, text=True).stdout.strip()
    return bool(o)

if __name__ == "__main__":
    main()
