# Handoff → local chat "Flow Connector local setup verification"

**Goal:** generate 7 vertical clips in Google Flow for the 12 Oct 2026 reel
*"Diwali is 4 weeks away. Is your society fire-ready?"* and push them to this repo.
Everything else (captions, logo on every frame, footer, CTA, audio, cover, caption,
hashtags, staging, publishing on Mon 12 Oct 08:24 IST) is already prepared and tested.

Deadline: clips in the repo before **Sun 11 Oct 2026, 23:00 IST** (anything later still
works until Mon 08:00 IST; after that the standard fallback posts).

## 1. Flow settings
Google Flow (already signed in, tab open) → new project **"ASZ Diwali reel 12 Oct"** →
Text-to-video, **aspect ratio 9:16 (portrait)**, 8 s, highest quality available, 1 output
per prompt (regenerate once if the first is off-brief). Keep native audio. Download MP4.

Reject a clip if it shows: readable text/signs, a real brand/logo, a child's face, an
actual fire or injury, anything that looks like a specific real building. These are
illustrative AI clips and must not read as a real site or customer.

## 2. The seven prompts (name the download exactly)
| file | prompt |
|---|---|
| clip-01.mp4 | Vertical 9:16 cinematic shot, a Mumbai high-rise housing society compound at dusk, rows of lit clay diyas along balcony railings and the compound wall, warm fairy lights on the building, slow dolly-in, realistic photography, warm tones, no text, no readable signs, no close-up faces |
| clip-02.mp4 | Vertical 9:16 close-up, a single lit clay diya on an apartment window sill, a sheer white curtain moving gently in the breeze dangerously close to the flame, shallow depth of field, warm evening light, slow push-in, realistic, no text |
| clip-03.mp4 | Vertical 9:16, adult hands holding lit sparklers in an open housing-society compound at night, a steel bucket of water and sand on the ground beside them, parked cars far away in the background, festive bokeh lights, realistic, no faces, no text |
| clip-04.mp4 | Vertical 9:16 macro, a red ABC dry-powder fire extinguisher mounted on a corridor wall of an Indian residential building, pressure gauge needle in the green zone, a technician's gloved hand tapping the gauge and checking the tag, clean modern corridor, realistic, no readable text |
| clip-05.mp4 | Vertical 9:16, a fire hydrant cabinet in an Indian residential building stairwell with a red landing valve and hose reel, then a steel fire duct door swinging shut, well-lit clean corridor, slow pan, realistic, no text |
| clip-06.mp4 | Vertical 9:16, a clean, empty refuge floor and open staircase of a modern Indian high-rise housing society, no stored items, green exit sign glowing, a safety inspector in a reflective vest walking through, realistic, no readable text, no logos |
| clip-07.mp4 | Vertical 9:16, a fire-safety technician in a reflective orange vest and white helmet checking a fire alarm control panel and a ceiling sprinkler head in a housing-society lobby, clipboard in hand, warm Diwali lights visible through the glass door behind, realistic, no readable text, no logos |

(Same prompts live in `studio/brief-2026-10-12-diwali-fire-ready.json` → `flow_prompts`.)

## 3. Push the clips
Either in the browser — https://github.com/anil-mourya/asz-reels/upload/main/flow/2026-10-12-diwali-fire-ready
(drag the 7 files, Commit) — or from a terminal:

    git clone --depth 1 https://github.com/anil-mourya/asz-reels
    copy clip-0*.mp4 asz-reels\flow\2026-10-12-diwali-fire-ready\
    cd asz-reels && git add flow && git -c user.name="ASZ Reels Studio" -c user.email="assafetyzone@gmail.com" commit -m "Flow clips: 12 Oct Diwali reel" && git push origin main

Do NOT run the assembly locally and do NOT publish anything. Reply in the Cowork chat
"clips pushed" (or just leave them: the Monday 08:24 IST run assembles, verifies and
posts the Flow version itself; if no clips are there it posts the verified standard
version that is already staged).

## 4. Optional, same day: hand the assembled Flow version back for verification
If a cloud session is available after the push, it runs
`python3 studio/assemble.py --brief studio/brief-2026-10-12-diwali-fire-ready.json --clips flow/2026-10-12-diwali-fire-ready --out reels/2026-10-12-diwali-fire-ready-flow.mp4 --cover covers/2026-10-12-diwali-fire-ready-flow.jpg --check-dir /tmp/chk`,
checks the frames, uploads both with `upload_marketing_asset_from_url`, and writes the
asset ids into `queue/2026-10-12-diwali-fire-ready.json` → `flowVersion`.
