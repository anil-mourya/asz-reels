#!/usr/bin/env python3
"""ASZ Reels Studio — standard (no-footage) reel renderer.

Usage:
  python3 studio/render_standard.py --cards studio/cards-<slug>.json \
      --out reels/<slug>.mp4 --cover covers/<slug>.jpg --check-dir /tmp/chk

Renders a sequence of caption cards over a navy/deep-red gradient background
(no site footage this run). Every frame carries the logo on a white rounded
card, top-centre, ~560px wide; the last card carries a large logo CTA card.
Output: 1080x1920, 24fps, H.264 yuv420p, AAC silent audio bed, <=12MB,
-movflags +faststart.
"""
import argparse, json, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GF = "/usr/share/fonts/truetype/google-fonts"
W, H, FPS = 1080, 1920, 24

def F(weight, size):
    return ImageFont.truetype(f"{GF}/Poppins-{weight}.ttf", size)

SAFFRON = (255, 176, 32)
NAVY = (12, 20, 38)
MAROON = (58, 10, 14)
WHITE = (255, 255, 255)

def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines

def gradient_bg():
    y = np.linspace(0, 1, H)[:, None]  # (H,1)
    x = np.linspace(-1, 1, W)[None, :]  # (1,W)
    base = np.zeros((H, W, 3), np.float32)
    for c in range(3):
        base[..., c] = NAVY[c] * (1 - y) + MAROON[c] * y
    glow = np.exp(-((x * 1.1) ** 2 + ((y - 0.32) * 2.4) ** 2))  # (H,W)
    glow_color = np.array([150, 70, 20], np.float32)
    img = base + glow[..., None] * glow_color[None, None, :] * 0.5
    img = np.clip(img, 0, 255)
    return Image.fromarray(img.astype(np.uint8)).convert("RGBA")

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
    card.paste(lg, (S + pad, S + pad), lg if lg.mode == "RGBA" else None)
    return card, S

def footer(draw):
    f = F("Medium", 28)
    txt = "A S SAFETYZONE  ·  assafetyzone.com"
    draw.text((W / 2, H - 70), txt, font=f, fill=(235, 235, 235), anchor="mm")

def render_card(logo, text, kind="body", sub=None):
    base = gradient_bg()
    d = ImageDraw.Draw(base)

    # logo card, top-centre, every frame
    big_cta = kind == "cta"
    lw = 760 if big_cta else 560
    card, S = logo_card(logo, lw, 28 if big_cta else 20, 24)
    cx = (W - card.width) // 2
    cy = 260 if big_cta else 90
    base.alpha_composite(card, (cx, cy))

    text_top = cy + card.height + (120 if big_cta else 90)

    if kind == "hook":
        font = F("Bold", 92)
        color = SAFFRON
    elif kind == "cta":
        font = F("Bold", 70)
        color = WHITE
    else:
        font = F("Bold", 66)
        color = WHITE

    max_w = W - 160
    lines = wrap(d, text, font, max_w)
    line_h = font.size * 1.28
    total_h = line_h * len(lines)
    y = text_top if kind != "cta" else text_top
    if kind != "cta":
        y = (H * 0.52) - total_h / 2 if kind == "hook" else text_top
    for i, ln in enumerate(lines):
        d.text((W / 2, y + i * line_h), ln, font=font, fill=color, anchor="mm")

    if sub:
        fsub = F("Medium", 40)
        sub_lines = wrap(d, sub, fsub, max_w)
        sy = y + len(lines) * line_h + 50
        for i, ln in enumerate(sub_lines):
            d.text((W / 2, sy + i * 52), ln, font=fsub, fill=(225, 225, 230), anchor="mm")

    footer(d)
    return base.convert("RGB")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cover", required=True)
    ap.add_argument("--check-dir", default="/tmp/chk")
    args = ap.parse_args()

    with open(args.cards) as f:
        spec = json.load(f)

    logo = Image.open(os.path.join(ROOT, "brand", "logo.jpg")).convert("RGBA")

    tmp = os.path.join("/tmp", "asz_render_tmp")
    os.makedirs(tmp, exist_ok=True)
    os.makedirs(args.check_dir, exist_ok=True)

    clip_paths = []
    frame_idx = 0
    for i, card in enumerate(spec["cards"]):
        img = render_card(logo, card["text"], card.get("kind", "body"), card.get("sub"))
        png = os.path.join(tmp, f"card_{i:02d}.png")
        img.save(png)
        clip = os.path.join(tmp, f"clip_{i:02d}.mp4")
        dur = card["dur"]
        fade = min(0.35, dur / 4)
        run([
            "ffmpeg", "-y", "-loop", "1", "-i", png, "-t", str(dur),
            "-vf", f"fps={FPS},fade=t=in:st=0:d={fade},fade=t=out:st={max(0, dur - fade)}:d={fade},format=yuv420p",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", clip,
        ])
        clip_paths.append(clip)
        if i in (0, len(spec["cards"]) // 2, len(spec["cards"]) - 1):
            frame_png = os.path.join(args.check_dir, f"frame_{frame_idx:02d}.png")
            img.save(frame_png)
            frame_idx += 1

    concat_list = os.path.join(tmp, "concat.txt")
    with open(concat_list, "w") as f:
        for c in clip_paths:
            f.write(f"file '{c}'\n")

    silent_video = os.path.join(tmp, "video_only.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", silent_video])

    total_dur = sum(c["dur"] for c in spec["cards"])
    run([
        "ffmpeg", "-y", "-i", silent_video,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-c:v", "copy", "-c:a", "aac", "-shortest", "-movflags", "+faststart",
        args.out,
    ])

    # cover: first strong frame (hook card) at full res
    cover_img = render_card(logo, spec["cards"][0]["text"], spec["cards"][0].get("kind", "body"), spec["cards"][0].get("sub"))
    cover_img.save(args.cover, "JPEG", quality=90)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate",
         "-show_entries", "format=duration,size", "-of", "json", args.out],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(probe.stdout)
    streams = info["streams"]
    has_v = any(s["codec_type"] == "video" for s in streams)
    has_a = any(s["codec_type"] == "audio" for s in streams)
    vstream = next(s for s in streams if s["codec_type"] == "video")
    size_mb = float(info["format"]["size"]) / 1_000_000
    report = {
        "verified": has_v and has_a and vstream["width"] == 1080 and vstream["height"] == 1920,
        "width": vstream["width"], "height": vstream["height"],
        "duration": float(info["format"]["duration"]),
        "size_mb": round(size_mb, 2),
        "has_video": has_v, "has_audio": has_a,
        "cards": len(spec["cards"]),
    }
    print(json.dumps(report, indent=2))
    if not report["verified"]:
        sys.exit("VERIFICATION FAILED")

if __name__ == "__main__":
    main()
