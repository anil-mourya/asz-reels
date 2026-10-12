# Drop folder: Diwali v2 reel (real ASZ footage + your voice)

Upload here (GitHub web uploader: https://github.com/anil-mourya/asz-reels/upload/main/inbox/diwali-v2), named exactly:

| file | shot | what to record (vertical, 6–8 s, phone held steady, sound ON) |
|---|---|---|
| s1.mp4 | WIDE | Society exterior at dusk with Diwali lights / diyas on balconies. Still or slow pan. |
| s2.mp4 | WIDE | Two ASZ technicians in uniform walking into a lobby/compound with toolkit or checklist. From behind or side. |
| s3.mp4 | CLOSE | Finger on the pressure gauge of a stored-pressure ABC extinguisher, needle in green. Hold 3 s in focus. |
| s4.mp4 | CLOSE | Technician turning the extinguisher's service tag to read the last service date. |
| s5.mp4 | MEDIUM | Hydrant cabinet / hose reel on a landing: cabinet opened, path to it clear. |
| s6.mp4 | WIDE | Staircase or refuge area, technician walking through, nothing stored. |
| s7.mp4 | CLOSE | Shaft (duct) door being closed until it latches — keep the latch sound. |
| s8.mp4 | CLOSE | Fire alarm panel front showing normal / healthy, hand near it, no fault lights. |
| s9.mp4 | WIDE | Technician ticking the checklist, then a wide of the lit compound. |
| voice.m4a | VO | Your voice, one take — script in studio/VO-SCRIPT-2026-10-12-diwali-v2.md |

Rules: only your own team and a site that has agreed to be filmed; no society name board, flat
numbers or resident faces unless you have their written OK; nothing staged as a "completed
inspection" that did not happen. Then run:

    python3 studio/render_v2.py --edit studio/edit-2026-10-12-diwali-v2.json \
      --out reels/2026-10-12-diwali-v2.mp4 --cover covers/2026-10-12-diwali-v2.jpg --check-dir /tmp/chk

A render with any missing shot or no voice is marked PREVIEW and must not be posted.
