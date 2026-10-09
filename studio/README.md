# studio/ — Reels Studio assembly

`assemble.py` turns a brief (`brief-<slug>.json`) into a branded 1080×1920 reel + cover:
logo card on every frame (top-centre, ~560 px, untouched), caption band per card, footer,
final CTA card with the big logo, AAC audio (clip audio + soft bed, or bed alone).

    python3 studio/assemble.py --brief studio/brief-<slug>.json                      # standard gradient look
    python3 studio/assemble.py --brief studio/brief-<slug>.json --clips flow/<slug>   # Flow/owner clips as backgrounds

Outputs `reels/<slug>.mp4`, `covers/<slug>.jpg`, prints a JSON report with `verified: true`
(1080×1920, 25–40 s, 1 video + 1 audio stream, ≤ 12 MB) and exits non-zero otherwise.
Needs ffmpeg, Pillow, numpy (all present in the Reels Studio cloud run).

`../queue/<slug>.json` tells the scheduled Reels Studio run which prepared reel to publish
at its next slot instead of rendering a fresh one. See the manifest's `rule`.
