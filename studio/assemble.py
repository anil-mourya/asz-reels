#!/usr/bin/env python3
"""ASZ Reels Studio — assemble a branded 1080x1920 reel from a brief.

    python3 studio/assemble.py --brief studio/brief-<slug>.json \
        [--clips flow/<slug>] [--audio auto|bed|clips|silent] \
        [--out reels/<slug>.mp4] [--cover covers/<slug>.jpg]

With --clips, each card's background is the Flow clip named in the brief
(scaled/cropped to 9:16, blurred pad for landscape, slow zoom). Without it,
every card sits on a navy/deep-red gradient with warm bokeh — the "standard"
look. In both cases: logo card on EVERY frame (top-centre, white rounded card,
~560 px wide, never recoloured/cropped/stretched), caption band, footer,
final CTA card with the big logo, and an AAC audio track.

Needs ffmpeg/ffprobe, Pillow, numpy. Run from the asz-reels repo root.
"""
import argparse, json, math, os, shutil, subprocess, sys, tempfile, wave
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import numpy as np

FONT_DIR = "/usr/share/fonts/opentype/inter"
def font(name, size):
    for cand in (os.path.join(FONT_DIR, f"Inter-{name}.otf"),
                 os.path.join(FONT_DIR, f"InterDisplay-{name}.otf"),
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(cand):
            return ImageFont.truetype(cand, size)
    return ImageFont.load_default()

RED = (230, 59, 46); AMBER = (245, 166, 35); WHITE = (255, 255, 255)

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-4000:])
        raise SystemExit(f"command failed: {' '.join(cmd[:6])} …")
    return r.stdout

def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_entries",
               "stream=codec_type,width,height,r_frame_rate:format=duration,size",
               "-of", "json", path])
    j = json.loads(out)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    return {"w": int(v["width"]) if v else 0, "h": int(v["height"]) if v else 0,
            "dur": float(j["format"].get("duration", 0)), "size": int(j["format"].get("size", 0)),
            "video": v is not None, "audio": a is not None, "n_video": sum(s["codec_type"] == "video" for s in j["streams"]),
            "n_audio": sum(s["codec_type"] == "audio" for s in j["streams"])}

# ---------- drawing ----------
def rounded_shadow_card(canvas, box, radius=36, fill=WHITE, shadow=(0, 0, 0, 110), blur=28, offset=(0, 14)):
    x0, y0, x1, y1 = box
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    d.rounded_rectangle((x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]), radius, fill=shadow)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(sh)
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(box, radius, fill=fill + ((255,) if len(fill) == 3 else ()))

def place_logo(canvas, logo, width, cy_top, pad=36):
    """White rounded card with soft shadow, logo scaled proportionally to `width` (no crop, no recolour)."""
    W = canvas.size[0]
    lw = width; lh = round(logo.size[1] * width / logo.size[0])
    lg = logo.resize((lw, lh), Image.LANCZOS)
    cw, ch = lw + 2 * pad, lh + 2 * pad
    x0 = (W - cw) // 2; y0 = cy_top
    rounded_shadow_card(canvas, (x0, y0, x0 + cw, y0 + ch), radius=40 if width < 700 else 56)
    canvas.paste(lg, (x0 + pad, y0 + pad))
    return y0 + ch

def wrap(draw, text, fnt, max_w):
    words = text.split(); lines = []; cur = ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= max_w: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def footer(canvas, text):
    W, H = canvas.size
    d = ImageDraw.Draw(canvas)
    # accent line: red → amber
    y = H - 180
    for i, x in enumerate(range(120, W - 120)):
        t = (x - 120) / (W - 240)
        col = tuple(round(RED[k] * (1 - t) + AMBER[k] * t) for k in range(3)) + (230,)
        d.line((x, y, x, y + 2), fill=col)
    f = font("Medium", 30)
    tw = d.textlength(text, font=f)
    d.text(((W - tw) / 2, y + 26), text, font=f, fill=(255, 255, 255, 225))

def logo_overlay(brief, logo):
    W, H = brief["width"], brief["height"]
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # scrims so the logo card and footer read over bright footage
    sc = np.zeros((H, W, 4), dtype=np.uint8)
    top = np.clip((380 - np.arange(H)) / 380, 0, 1) * 120; bot = np.clip((np.arange(H) - 1560) / 360, 0, 1) * 150
    sc[:, :, 3] = np.minimum(top + bot, 255).astype(np.uint8)[:, None]
    ov.alpha_composite(Image.fromarray(sc, "RGBA"))
    place_logo(ov, logo, 560, 72)
    footer(ov, brief["footer"])
    return ov

def band_overlay(brief, card, total):
    W, H = brief["width"], brief["height"]
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    fk = font("SemiBold", 34); ft = font("Bold", 78); fc = font("Medium", 28)
    bx0, bx1 = 60, W - 60; pad = 48
    lines = wrap(d, card["text"], ft, bx1 - bx0 - 2 * pad - 20)
    if len(lines) > 3:
        ft = font("Bold", 66); lines = wrap(d, card["text"], ft, bx1 - bx0 - 2 * pad - 20)
    lh = ft.size + 14
    bh = pad + 34 + 26 + len(lines) * lh + 20 + pad
    by0 = int(H * 0.50 - bh / 2); by1 = by0 + bh
    # band
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0)); bd = ImageDraw.Draw(band)
    bd.rounded_rectangle((bx0, by0, bx1, by1), 30, fill=(12, 16, 34, 218))
    ov.alpha_composite(band)
    d = ImageDraw.Draw(ov)
    d.rounded_rectangle((bx0 - 6, by0 + 40, bx0 + 8, by1 - 40), 6, fill=RED + (255,))
    # kicker (letter-spaced)
    x = bx0 + pad; y = by0 + pad
    kick = "  ".join(card["kicker"]) if False else card["kicker"]
    kw = d.textlength(kick, font=fk) + 2 * (len(kick) - 1)
    cx = (bx0 + bx1) / 2 - kw / 2
    for ch in kick:
        d.text((cx, y), ch, font=fk, fill=AMBER + (255,)); cx += d.textlength(ch, font=fk) + 2
    y += 34 + 26
    for ln in lines:
        tw = d.textlength(ln, font=ft)
        d.text(((bx0 + bx1) / 2 - tw / 2, y), ln, font=ft, fill=WHITE + (255,))
        y += lh
    cnt = f"{card['n']} / {total}"
    d.text((bx1 - pad - d.textlength(cnt, font=fc), by1 - pad - 10), cnt, font=fc, fill=(255, 255, 255, 170))
    return ov

def cta_overlay(brief, logo):
    W, H = brief["width"], brief["height"]; c = brief["cta"]
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bottom = place_logo(ov, logo, 900, 520, pad=44)
    d = ImageDraw.Draw(ov)
    fh = font("Bold", 80); fb = font("SemiBold", 42); f1 = font("Medium", 34); f2 = font("Medium", 31)
    y = bottom + 90
    for ln in wrap(d, c["headline"], fh, W - 160):
        tw = d.textlength(ln, font=fh); d.text(((W - tw) / 2, y), ln, font=fh, fill=WHITE + (255,)); y += 94
    y += 24
    bw = int(d.textlength(c["button"], font=fb)) + 120; bh = 104
    d.rounded_rectangle(((W - bw) / 2, y, (W + bw) / 2, y + bh), 28, fill=RED + (255,))
    d.text(((W - d.textlength(c["button"], font=fb)) / 2, y + 26), c["button"], font=fb, fill=WHITE + (255,))
    y += bh + 44
    for txt, f in ((c["line1"], f1), (c["line2"], f2)):
        for ln in wrap(d, txt, f, W - 200):
            tw = d.textlength(ln, font=f); d.text(((W - tw) / 2, y), ln, font=f, fill=(255, 255, 255, 225)); y += f.size + 12
    footer(ov, brief["footer"])
    return ov

def gradient_bg(brief, seed, scale=1.5):
    """Navy → deep red gradient with warm bokeh glows (Diwali-tinted standard look)."""
    W, H = int(brief["width"] * scale), int(brief["height"] * scale)
    rng = np.random.default_rng(seed)
    yy = np.linspace(0, 1, H)[:, None]; xx = np.linspace(0, 1, W)[None, :]
    top = np.array([10, 16, 46]); mid = np.array([74, 16, 30]); bot = np.array([16, 8, 14])
    t = yy
    col = np.where(t < 0.6, top + (mid - top) * (t / 0.6), mid + (bot - mid) * ((t - 0.6) / 0.4))
    diag = 0.12 * np.sin(2 * math.pi * (xx * 0.6 + yy * 0.4 + rng.random()))
    img = np.clip(col[:, None, :] * (1 + diag)[:, :, None], 0, 255).astype(np.uint8)
    base = Image.fromarray(img, "RGB").convert("RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); g = ImageDraw.Draw(glow)
    for _ in range(4):
        r = int(rng.integers(220, 420) * scale); x = int(rng.integers(0, W)); y = int(rng.integers(int(H * 0.15), H))
        g.ellipse((x - r, y - r, x + r, y + r), fill=AMBER + (70,))
    for _ in range(28):  # tiny diya-like points
        r = int(rng.integers(3, 7) * scale); x = int(rng.integers(0, W)); y = int(rng.integers(int(H * 0.55), H))
        g.ellipse((x - r, y - r, x + r, y + r), fill=(255, 210, 120, 200))
    glow = glow.filter(ImageFilter.GaussianBlur(int(90 * scale)))
    base.alpha_composite(glow)
    return base.convert("RGB")

# ---------- audio ----------
def synth_bed(duration, card_times, sr=44100):
    n = int(duration * sr); t = np.arange(n) / sr
    pad = np.zeros(n)
    for f, a in ((110.0, .55), (164.8, .35), (220.0, .25), (329.6, .12)):
        pad += a * np.sin(2 * np.pi * f * t + np.random.default_rng(int(f)).random() * 6.28)
    pad *= 0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t)       # slow swell
    pad *= 0.5 + 0.5 * (1 - np.exp(-t / 2.0))              # ease in
    # soft chime at each card change
    for ct in card_times[1:]:
        i0 = int(ct * sr); L = int(0.9 * sr)
        if i0 + L > n: L = n - i0
        tt = np.arange(L) / sr
        pad[i0:i0 + L] += 0.9 * np.exp(-tt * 4.5) * (np.sin(2 * np.pi * 1318.5 * tt) + 0.5 * np.sin(2 * np.pi * 1975.5 * tt))
    fade = int(1.5 * sr); pad[-fade:] *= np.linspace(1, 0, fade)
    pad = pad / (np.abs(pad).max() + 1e-9) * 0.22            # ≈ −13 dBFS peak, a bed not a lead
    return pad

def write_wav(path, x, sr=44100):
    x16 = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(x16.tobytes())

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", required=True); ap.add_argument("--clips", default=None)
    ap.add_argument("--audio", default="auto", choices=["auto", "bed", "clips", "silent"])
    ap.add_argument("--out", default=None); ap.add_argument("--cover", default=None)
    ap.add_argument("--check-dir", default=None, help="write 3 verification frames here")
    args = ap.parse_args()

    brief = json.load(open(args.brief)); slug = brief["slug"]
    W, H, fps = brief["width"], brief["height"], brief["fps"]
    out = args.out or f"reels/{slug}.mp4"; cover = args.cover or f"covers/{slug}.jpg"
    if not os.path.exists(brief["logo"]):
        raise SystemExit("LOGO UNAVAILABLE — do not post (brand/logo.jpg missing)")
    logo = Image.open(brief["logo"]).convert("RGB")
    tmp = tempfile.mkdtemp(prefix="aszreel-")
    cards = brief["cards"]; total = len(cards)

    logo_png = os.path.join(tmp, "logo.png"); logo_overlay(brief, logo).save(logo_png)
    cta_png = os.path.join(tmp, "cta.png"); cta_overlay(brief, logo).save(cta_png)

    segs = []; times = [0.0]; clip_audio = []
    for c in cards:
        dur = float(c["dur"]); band = os.path.join(tmp, f"band{c['n']}.png"); band_overlay(brief, c, total).save(band)
        seg = os.path.join(tmp, f"seg{c['n']:02d}.mp4")
        clip = os.path.join(args.clips, c["clip"]) if args.clips else None
        if clip and os.path.exists(clip):
            p = probe(clip); landscape = p["w"] / max(p["h"], 1) > (W / H) * 1.02
            nfr = int(dur * fps); W2, H2 = int(W * 1.1) // 2 * 2, int(H * 1.1) // 2 * 2
            zoom = f"scale={W2}:{H2},zoompan=z='1+0.06*in/{nfr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"
            if landscape:
                vf = (f"[0:v]split=2[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=32,eq=brightness=-0.12[bg];"
                      f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,{zoom}[v0]")
            else:
                vf = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{zoom}[v0]"
            cmd = ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", clip,
                   "-loop", "1", "-i", logo_png, "-loop", "1", "-i", band,
                   "-filter_complex", vf + f";[2:v]format=rgba,fade=t=in:st=0:d=0.3:alpha=1[bd];"
                   f"[v0][1:v]overlay=0:0[v1];[v1][bd]overlay=0:0,fps={fps},format=yuv420p[v]",
                   "-map", "[v]", "-t", f"{dur}", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                   "-r", str(fps), "-pix_fmt", "yuv420p", seg]
            run(cmd)
            if p["audio"]:
                wav = os.path.join(tmp, f"aud{c['n']:02d}.wav")
                run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", clip, "-t", f"{dur}", "-vn",
                     "-ac", "1", "-ar", "44100", "-af", f"afade=t=in:st=0:d=0.3,afade=t=out:st={dur-0.3}:d=0.3", wav])
                clip_audio.append((times[-1], dur, wav))
        else:
            bg = os.path.join(tmp, f"bg{c['n']}.png"); gradient_bg(brief, seed=100 + c["n"]).save(bg)
            frames = int(dur * fps)
            vf = (f"[0:v]zoompan=z='1+0.10*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={fps}[v0];"
                  f"[2:v]format=rgba,fade=t=in:st=0:d=0.3:alpha=1[bd];[v0][1:v]overlay=0:0[v1];[v1][bd]overlay=0:0,format=yuv420p[v]")
            run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", bg, "-loop", "1", "-i", logo_png, "-loop", "1", "-i", band,
                 "-filter_complex", vf, "-map", "[v]", "-t", f"{dur}", "-an", "-c:v", "libx264", "-preset", "medium",
                 "-crf", "20", "-r", str(fps), "-pix_fmt", "yuv420p", seg])
        segs.append(seg); times.append(times[-1] + dur)

    # CTA card on the standard gradient (brand card, same in both modes)
    cdur = float(brief["cta"]["dur"]); bg = os.path.join(tmp, "bgcta.png"); gradient_bg(brief, seed=7).save(bg)
    frames = int(cdur * fps); seg = os.path.join(tmp, "seg99.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", bg, "-loop", "1", "-i", cta_png, "-filter_complex",
         f"[0:v]zoompan=z='1+0.06*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={fps}[v0];"
         f"[1:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1[ov];[v0][ov]overlay=0:0,format=yuv420p[v]",
         "-map", "[v]", "-t", f"{cdur}", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(fps),
         "-pix_fmt", "yuv420p", seg])
    segs.append(seg); total_dur = times[-1] + cdur

    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
    video = os.path.join(tmp, "video.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video])

    # audio
    mode = args.audio
    if mode == "auto": mode = "clips" if clip_audio else "bed"
    sr = 44100; n = int(total_dur * sr)
    if mode == "silent":
        mix = np.zeros(n)
    else:
        mix = synth_bed(total_dur, times, sr)
        if mode == "clips":
            mix *= 0.45  # bed sits under the clips' own sound
            for start, dur, wav in clip_audio:
                with wave.open(wav) as w:
                    x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float) / 32767
                i0 = int(start * sr); x = x[: n - i0]
                mix[i0:i0 + len(x)] += 0.6 * x
        mix = mix / max(1.0, np.abs(mix).max() / 0.8)
    wav = os.path.join(tmp, "mix.wav"); write_wav(wav, mix, sr)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True); os.makedirs(os.path.dirname(cover) or ".", exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", wav, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out])
    # size guard: Instagram-friendly ≤ 12 MB — re-encode harder only if needed
    crf = 20
    while probe(out)["size"] > 12_000_000 and crf < 30:
        crf += 3; tmpout = out + ".tmp.mp4"
        run(["ffmpeg", "-v", "error", "-y", "-i", out, "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
             "-maxrate", "2800k", "-bufsize", "5600k", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", tmpout])
        os.replace(tmpout, out)
    # cover = hook card after the band has faded in
    run(["ffmpeg", "-v", "error", "-y", "-ss", "1.2", "-i", segs[0], "-frames:v", "1", "-q:v", "2", cover])

    # verify
    p = probe(out); pc = Image.open(cover)
    ok = (p["w"], p["h"]) == (W, H) and p["n_video"] == 1 and p["n_audio"] == 1 and 25 <= p["dur"] <= 40 and p["size"] <= 12_000_000 and pc.size == (W, H)
    if args.check_dir:
        os.makedirs(args.check_dir, exist_ok=True)
        for name, ss in (("f-hook.jpg", "1.5"), ("f-mid.jpg", f"{total_dur/2:.1f}"), ("f-cta.jpg", f"{total_dur-1.5:.1f}")):
            run(["ffmpeg", "-v", "error", "-y", "-ss", ss, "-i", out, "-frames:v", "1", "-vf", "scale=360:-1", os.path.join(args.check_dir, name)])
    report = {"out": out, "cover": cover, "width": p["w"], "height": p["h"], "duration_s": round(p["dur"], 2),
              "size_bytes": p["size"], "video_streams": p["n_video"], "audio_streams": p["n_audio"], "audio_mode": mode,
              "footage": "flow-clips" if clip_audio or (args.clips and any(os.path.exists(os.path.join(args.clips, c["clip"])) for c in cards)) else "standard-gradient",
              "clips_used": [c["clip"] for c in cards if args.clips and os.path.exists(os.path.join(args.clips, c["clip"]))],
              "cover_size": pc.size, "verified": ok}
    print(json.dumps(report, indent=1))
    shutil.rmtree(tmp, ignore_errors=True)
    if not ok: raise SystemExit("VERIFY FAILED")

if __name__ == "__main__":
    main()
