#!/usr/bin/env python3
"""ASZ unattended footage-led renderer. No publishing credentials or network calls.

python3 studio/pro_renderer.py render --manifest studio/manifests/<slot>.json
python3 studio/pro_renderer.py gate --manifest ... --review studio/qa/<slot>-review.json
python3 studio/pro_renderer.py reserve --manifest ... --review ...
python3 studio/pro_renderer.py record --manifest ... --status posted --media-id ... --permalink ...
"""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageChops

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.1"
REVIEW_CHECKS = ("footage_matches_copy", "single_clean_logo", "captions_readable", "no_old_overlays",
                 "audio_appropriate", "cover_matches_video", "no_false_claims", "history_checked")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local(path):
    resolved = (ROOT / path).resolve()
    require(resolved.is_relative_to(ROOT), "Path must stay inside the media repository")
    return resolved


def read(path):
    return json.loads(local(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = local(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def digest(path):
    return hashlib.sha256(local(path).read_bytes()).hexdigest()


def command(args, timeout=120):
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    require(result.returncode == 0, result.stderr.decode(errors="replace")[-2500:])
    return result


def ffmpeg():
    executable = os.environ.get("ASZ_FFMPEG") or shutil.which("ffmpeg")
    require(executable, "ffmpeg unavailable; stop, do not use a card-only fallback")
    return str(executable)


def font(size, bold=False):
    candidates = (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf"]
                  if bold else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/segoeui.ttf"])
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise ValueError("Readable TrueType font unavailable")


def fingerprint(manifest):
    editorial = {key: manifest[key] for key in ("assetId", "shots", "speed", "caption")}
    return hashlib.sha256(json.dumps(editorial, sort_keys=True).encode()).hexdigest()


def validate(manifest, catalog=None, verify_files=True):
    catalog = catalog or read("studio/asset-library.json")
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]{3,70}", manifest["slot"]), "Invalid slot name")
    asset = catalog["assets"][manifest["assetId"]]
    require(asset["reviewed"] and asset["rights"] and asset["sourceType"] in ("owner-archive", "owner-original"), "Unreviewed source or missing rights")
    require(isinstance(manifest["speed"], (int, float)) and .7 <= manifest["speed"] <= 1.0, "Invalid playback speed")
    require(4 <= len(manifest["shots"]) <= 7, "Use 4-7 purposeful shots")
    require(manifest["caption"] in asset["approvedPostCaptions"], "Post caption has not been checked against this footage")
    total = 0
    for shot in manifest["shots"]:
        scene = asset["scenes"][shot["scene"]]
        require(shot["lines"] in scene["approvedLines"], "On-screen copy is not approved for this visible action")
        require(all(isinstance(shot[k], (int, float)) and math.isfinite(shot[k]) for k in ("start", "duration")), "Invalid shot timing")
        require(shot["duration"] >= 2 and shot["start"] >= scene["start"] and shot["start"] + shot["duration"] <= scene["end"] + .001, "Shot outside reviewed clean window")
        require(shot["crop"] in scene["cleanCrops"], "Crop has not been reviewed for old overlays and visible action")
        w, h, x, y = shot["crop"]
        require(all(isinstance(v, int) and v >= 0 for v in shot["crop"]) and w > 0 and h > 0 and x+w <= asset["width"] and y+h <= asset["height"], "Invalid crop")
        require(abs((w/h)/(1080/1380)-1) < .015, "Crop would stretch the source")
        require(1 <= len(shot["lines"]) <= 2, "Too many caption lines")
        for line in shot["lines"]:
            require(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(line, font=font(60, True)) <= 952, "Caption exceeds safe width")
        total += shot["duration"] / manifest["speed"]
    require(18 <= total <= 35, "Reel must be 18-35 seconds")
    if verify_files:
        require(digest(asset["path"]) == asset["sha256"], "Source changed; visually re-review before use")
        require(digest("brand/logo.jpg") == catalog["logoSha256"], "Original logo missing or changed")
    return asset


def paths(manifest):
    slot = manifest["slot"]
    return {"video": f"reels/{slot}.mp4", "cover": f"covers/{slot}.jpg", "contactSheet": f"studio/qa/{slot}-contact.jpg", "qa": f"studio/qa/{slot}.json"}


def duplicate_check(manifest):
    ledger = read("marketing/publication-log.json")
    for entry in ledger.get("entries", []):
        same = entry.get("campaignId") == manifest["slot"] or entry.get("contentFingerprint") == fingerprint(manifest)
        require(not same, "This slot or exact edit already has a publication record; reconcile it, never blindly republish")
    return ledger


def overlay(shot, is_last, destination, source_type="owner-archive"):
    canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1080, 429), fill="#111823")
    draw.rectangle((0, 1810, 1080, 1920), fill="#111823")
    draw.rounded_rectangle((230, 20, 850, 220), radius=28, fill="white")
    logo = Image.open(local("brand/logo.jpg")).convert("RGB")
    logo.thumbnail((560, 180), Image.Resampling.LANCZOS)
    canvas.paste(logo, ((1080-logo.width)//2, 35))
    for index, line in enumerate(shot["lines"]):
        draw.text((64, 244+index*70), line, font=font(60, True), fill="white")
    if is_last:
        draw.text((64, 388), "assafetyzone.com", font=font(29), fill="#F59138")
    else:
        draw.rounded_rectangle((64, 405, 206, 411), radius=3, fill="#F47A24")
    disclosure = "PREVIOUSLY RECORDED ASZ FOOTAGE" if source_type == "owner-archive" else "ASZ PROJECT FOOTAGE"
    draw.text((64, 1840), disclosure, font=font(26), fill="#B7C0CE")
    canvas.save(destination)


def frame(video, second):
    result = command([ffmpeg(), "-v", "error", "-ss", str(second), "-i", str(video), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], 40)
    return Image.open(io.BytesIO(result.stdout)).convert("RGB")


def media_qa(video, expected, manifest, output):
    # Decode the entire output, not just its container metadata.
    result = command([ffmpeg(), "-hide_banner", "-i", str(video), "-vf", "crop=1080:1380:0:430,blackdetect=d=0.12:pix_th=0.08:pic_th=0.98", "-af", "volumedetect", "-f", "null", "-"], 120)
    report = result.stderr.decode(errors="replace")
    duration_match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", report)
    require(duration_match, "Could not verify media duration")
    duration = int(duration_match[1])*3600 + int(duration_match[2])*60 + float(duration_match[3])
    mean = re.search(r"mean_volume: ([-\d.]+) dB", report)
    peak = re.search(r"max_volume: ([-\d.]+) dB", report)
    require(mean and peak, "Missing or silent audio")
    require(-38 <= float(mean[1]) <= -10 and -20 <= float(peak[1]) <= -.5, "Audio is too quiet, too loud or clipping")
    require(18 <= duration <= 35 and abs(duration-expected) < .4, "Incorrect output duration")
    require(re.search(r"Video: h264.*yuv420p.*1080x1920.*24 fps", report), "Output encoding does not match the production profile")
    require("Audio: aac" in report and "black_start:" not in report, "Missing AAC audio or black footage detected")
    require(video.stat().st_size <= 12_000_000, "Output exceeds existing 12MB pipeline limit")
    samples = [0.0]
    cursor = 0.0
    for shot in manifest["shots"]:
        length = shot["duration"] / manifest["speed"]
        samples.extend([max(0, cursor+.12), min(duration-.30, cursor+length/2), min(duration-.30, cursor+length-.12)])
        cursor += length
    samples.append(duration-.30)
    sheet = Image.new("RGB", (1080, math.ceil(len(samples)/4)*512), "#eeeeee")
    brightness, motion = [], []
    for index, second in enumerate(samples):
        image = frame(video, second)
        require(image.size == (1080, 1920), "Unexpected frame size")
        active = image.crop((0, 430, 1080, 1810)).resize((108, 138)).convert("L")
        luminance = ImageStat.Stat(active).mean[0]
        require(luminance > 18, "Unacceptably dark image area")
        brightness.append(round(luminance, 1))
        if index > 0 and (index-1) % 3 == 2 and index <= 3*len(manifest["shots"]):
            difference = ImageStat.Stat(ImageChops.difference(previous, active)).mean[0]
            require(difference > .8, "Shot appears static; review source motion")
            motion.append(round(difference, 2))
        previous = active
        image.thumbnail((270, 480))
        x, y = (index % 4)*270, (index//4)*512
        sheet.paste(image, (x, y))
        ImageDraw.Draw(sheet).text((x+6, y+485), f"{second:.2f}s", fill="black")
    sheet.save(local(output["contactSheet"]), quality=90)
    frame(video, 1.2).save(local(output["cover"]), quality=92)
    return {"duration": duration, "sizeBytes": video.stat().st_size, "meanAudioDb": float(mean[1]), "peakAudioDb": float(peak[1]), "sampleTimes": samples, "imageLuma": brightness, "motionDifference": motion, "decodedCompletely": True, "blackIntervals": 0}


def render(manifest):
    asset = validate(manifest)
    duplicate_check(manifest)
    output = paths(manifest)
    for path in output.values():
        local(path).parent.mkdir(parents=True, exist_ok=True)
    require(not local(output["video"]).exists(), "Output already exists; review/reconcile it rather than overwrite an earlier attempt")
    speed = manifest["speed"]
    try:
        with tempfile.TemporaryDirectory(prefix="asz-pro-") as temporary:
            temporary = Path(temporary)
            for index, shot in enumerate(manifest["shots"]):
                layout = temporary / f"layout-{index}.png"
                overlay(shot, index == len(manifest["shots"])-1, layout, asset["sourceType"])
                crop = ":".join(map(str, shot["crop"]))
                vf = f"[0:v]crop={crop},scale=1080:1380,setsar=1,setpts=PTS/{speed},pad=1080:1920:0:430:color=0x111823[v];[v][1:v]overlay=0:0:format=auto,format=yuv420p[out]"
                command([ffmpeg(), "-y", "-v", "error", "-ss", str(shot["start"]), "-t", str(shot["duration"]), "-i", str(local(asset["path"])), "-loop", "1", "-i", str(layout), "-filter_complex", vf, "-map", "[out]", "-map", "0:a:0", "-af", f"atempo={speed},volume=2dB,alimiter=limit=0.84:level=0", "-r", "24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-maxrate", "4200k", "-bufsize", "8400k", "-threads", "2", "-c:a", "aac", "-b:a", "128k", "-t", str(shot["duration"]/speed), "-shortest", "-movflags", "+faststart", str(temporary/f"shot-{index}.mp4")])
                print(f"Rendered shot {index+1}/{len(manifest['shots'])}", flush=True)
            concat = temporary / "concat.txt"
            concat.write_text("".join(f"file 'shot-{i}.mp4'\n" for i in range(len(manifest["shots"]))), encoding="utf-8")
            command([ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-vf", "fps=24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-maxrate", "4200k", "-bufsize", "8400k", "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(local(output["video"]))], 120)
        return verify(manifest)
    except Exception as error:
        write(output["qa"], {"campaignId": manifest["slot"], "mechanicalPass": False, "publicationReady": False, "error": str(error)})
        raise


def verify(manifest):
    asset = validate(manifest)
    output = paths(manifest)
    write(output["qa"], {"campaignId": manifest["slot"], "mechanicalPass": False, "publicationReady": False, "status": "verifying"})
    evidence = media_qa(local(output["video"]), sum(s["duration"]/manifest["speed"] for s in manifest["shots"]), manifest, output)
    qa = {"rendererVersion": VERSION, "campaignId": manifest["slot"], "contentFingerprint": fingerprint(manifest), "mechanicalPass": True, "publicationReady": False, "needs": "Claude must visually inspect contact sheet, cover, and audio, then write the independent review and run gate", "paths": output, "videoSha256": digest(output["video"]), "coverSha256": digest(output["cover"]), "source": asset["path"], "sourceType": asset["sourceType"], "rights": asset["rights"], "audio": "Original source location audio; tempo-adjusted, levelled, limited", "shotToCaptionMap": [{"visibleAction": asset["scenes"][s["scene"]]["observation"], **s} for s in manifest["shots"]], "evidence": evidence}
    write(output["qa"], qa)
    local(f"studio/qa/{manifest['slot']}-caption.txt").write_text(manifest["caption"]+"\n", encoding="utf-8")
    return qa


def gate(manifest, review_path):
    validate(manifest)
    ledger = duplicate_check(manifest)
    output = paths(manifest)
    qa, review = read(output["qa"]), read(review_path)
    require(qa.get("mechanicalPass") is True, "Mechanical QA did not pass")
    require(qa["contentFingerprint"] == fingerprint(manifest), "Manifest changed after rendering")
    require(qa["videoSha256"] == digest(output["video"]) == review.get("videoSha256"), "Review must refer to the exact rendered video")
    require(qa["coverSha256"] == digest(output["cover"]), "Cover changed after QA")
    for key in REVIEW_CHECKS:
        require(review.get("checks", {}).get(key) is True, f"Missing or failed visual/history review: {key}")
    require(len(review.get("observations", [])) >= len(manifest["shots"]), "Record a visual observation for every shot")
    require(review.get("historyEvidence") and review.get("reviewer") and review.get("reviewedAt"), "Missing reviewer or publication history evidence")
    return ledger, qa, review


def reserve(manifest, review_path):
    ledger, qa, review = gate(manifest, review_path)
    entry = {"campaignId": manifest["slot"], "contentFingerprint": fingerprint(manifest), "status": "publishing", "reservedAt": datetime.now(timezone.utc).isoformat(), "theme": manifest["theme"], "sourceType": qa["sourceType"], "paths": qa["paths"], "videoSha256": qa["videoSha256"], "qaResult": "passed", "reviewPath": review_path, "mediaId": None, "permalink": None, "postedAt": None}
    ledger.setdefault("entries", []).append(entry)
    write("marketing/publication-log.json", ledger)
    write(f"queue/{manifest['slot']}.json", entry)
    return entry


def record(manifest, status, media_id, permalink, asset_id):
    ledger = read("marketing/publication-log.json")
    found = [entry for entry in ledger["entries"] if entry.get("campaignId") == manifest["slot"]]
    require(len(found) == 1, "Reserve this slot before publishing; ambiguous log")
    entry = found[0]
    if status == "posted":
        require(media_id and re.fullmatch(r"https://(?:www\.)?instagram\.com/(?:reel|p)/[A-Za-z0-9_-]+/?", permalink or ""), "Confirmed media ID and Instagram permalink are required")
        if entry["status"] == "posted":
            require(entry["mediaId"] == media_id and entry["permalink"] == permalink, "Conflicting publication result")
            return entry
    require(entry["status"] in ("publishing", "publication_unknown"), "Invalid publication transition")
    entry.update(status=status, assetId=asset_id, mediaId=media_id, permalink=permalink)
    if status == "posted":
        entry["postedAt"] = datetime.now(timezone.utc).isoformat()
    write("marketing/publication-log.json", ledger)
    write(f"queue/{manifest['slot']}.json", entry)
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["render", "verify", "gate", "reserve", "record"])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--review")
    parser.add_argument("--status", choices=["posted", "publication_unknown", "failed"])
    parser.add_argument("--media-id")
    parser.add_argument("--permalink")
    parser.add_argument("--asset-id")
    args = parser.parse_args()
    manifest = read(args.manifest)
    if args.action == "render":
        result = render(manifest)
    elif args.action == "verify":
        result = verify(manifest)
    elif args.action in ("gate", "reserve"):
        require(args.review, "An independent render review is required")
        result = reserve(manifest, args.review) if args.action == "reserve" else {"publicationReady": bool(gate(manifest, args.review)), "campaignId": manifest["slot"]}
    else:
        require(args.status, "A publication result is required")
        result = record(manifest, args.status, args.media_id, args.permalink, args.asset_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"BLOCKED: {error}")
