---
name: video-subtitler
description: Add accurate subtitles to videos from ASR or supplied subtitle files, producing a standalone SRT and matching transcript by default, with an optional burned-in video only on explicit request or post-delivery confirmation. Use when the user asks to 给视频加字幕, 生成字幕版视频, 重做字幕同步, add subtitles/captions, burn subtitles into a video, create fine-grained subtitles, or optionally add a horizontal dynamic module progress bar (which first delivers a YouTube/Bilibili chapters file). Requires fine-grained/word-level ASR rather than splitting coarse subtitles, semantic cue segmentation at phrase boundaries (not at raw audio-gap timing), slide-text (OCR) grounding for proper nouns and on-screen numbers, conservative proofreading, hallucination filtering, Simplified/Traditional Chinese script normalization, filler-word cleanup when requested, proper-noun/terminology review before final SRT delivery, and final SRT gate validation (plus ffprobe/frame validation when rendering).
---

# Video Subtitler

Create accurate subtitles without modifying the source video. The default deliverables are:

1. standalone `.srt`
2. matching transcript

A burned-in (processed) video is **opt-in**, never default: render only when (a) the user explicitly asked to burn upfront, or (b) the user answers yes when asked after the SRT/transcript delivery. In case (a) do not ask again.

If the user asks for a progress bar, first deliver the module segmentation as a chapters file (YouTube/Bilibili formats, see workflow §7b), then ask whether to burn; the reproducible filter/config file is generated only once burning is confirmed.

## Non-negotiables

- Never fake fine timing by mechanically splitting coarse subtitle cues.
- Prefer word-level or short-segment ASR timestamps, then rebuild short cues from that timing.
- Segment cues at semantic/phrase boundaries, not at raw audio-gap timing. Speakers pause mid-phrase, breathe between a word's syllables, and repeat connectors ("那那么", "来来"); audio gaps are not sentence boundaries. No cue may begin or end mid-phrase — rebalance tokens across adjacent cues (keeping timing monotonic) so each cue reads as one complete chunk. This is the single highest-leverage quality step; mis-segmentation, not wrong characters, is the dominant defect in raw ASR cues.
- When the video shows slides or on-screen text, OCR it and use it as the strongest available grounding source for visible proper nouns and on-screen numbers (after confirming context). The screen usually spells out exactly the terms ASR mishears.
- Preserve the speaker's expression: fix recognition errors, terminology, hallucinations, script mismatches, and optional filler words; do not rewrite or polish.
- Treat ASR output as a draft only: remove platform hallucinations, repeated standalone filler hallucinations, empty/zero-duration nonsense, and other low-confidence garbage before final SRT/render.
- Normalize Chinese script: final Simplified Chinese subtitles/transcripts must not contain Traditional characters unless the user explicitly requests Traditional.
- Run proper-noun / terminology review before final SRT delivery (and therefore before any rendering). This is mandatory, not a nice little garnish.
- Before final SRT delivery (and again before rendering when rendering is requested), the full-coverage gate `scripts/validate_srt.py` must pass — run with the target script/language parameters; zero FAILs, and every WARNING covered by a disposition entry (see workflow §2c). Spot-checking is not a substitute.
- Never burn subtitles (or a progress bar) into the video without an explicit upfront request or a confirmed yes to the post-delivery question. After delivering the SRT/transcript (and chapters file if requested), ask the user once whether to burn.
- Use the persistent glossary (`scripts/glossary.py`): load it at intake, write newly verified terms back before the task ends. Verified once, reused in every later video.
- Keep the original video untouched; write new outputs to a task/output directory.
- Show visible checkpoints on long jobs: ASR done, subtitle draft done, proofreading done, validation done — plus render started/finished when rendering is requested.

## Workflow

Load `references/workflow.md` and follow it end to end.

## Default style

- Burned-in subtitle style: white text with black outline.
- Avoid white subtitle boxes unless explicitly requested.
- Chinese font preference: LXGW WenKai, commonly at `/Users/wsy/Library/Fonts/LXGWWenKai-Regular.ttf`.
- Place subtitles low enough to reduce content obstruction, but do not overlap controls/progress bars.

## Progress bar mode

Only act on a horizontal dynamic progress bar if the user asks for it — and even then, burning is confirmation-gated:

1. First produce the module segmentation and deliver it as a chapters file
   (YouTube description block + Bilibili manual-entry block, generated and
   validated by `scripts/chapters.py`; see workflow §7b).
2. Then ask the user whether to burn the progress bar (and subtitles) into the video.
3. Only on a confirmed yes, render with these rules:
   - Bar at the bottom when feasible.
   - Module names fixed inside their own bar segments.
   - Module names do not move with playback progress.
   - Include a visible moving progress fill/playhead.
   - Validate with adjacent-frame screenshots to confirm movement.

## Validation checklist

Always, before delivering the SRT/transcript:

- `scripts/validate_srt.py --dispositions ...` exits 0 (covers hallucination phrases, script-form residue, timing/structure, full-coverage segmentation flags).
- `scripts/glossary.py check` reports zero wrong-variant hits; report confirms this task's critical proper nouns are corrected.
- If a chapters file was requested: `scripts/chapters.py` exits 0 (0:00 start, ≥3 ascending chapters, ≥10 s each).
- Final response links the SRT and transcript (and chapters file if produced), and — unless the user already requested burning upfront — asks whether to burn.

Additionally, only when rendering happened:

- `ffprobe` output confirms duration, resolution, video stream, audio stream.
- Sample frames confirm subtitle style, placement, no major obstruction, progress bar behavior if enabled.
- Final response also links the processed video.

If the user later supplies a hand-fine-tuned SRT, run the retrospective loop (workflow §11): `scripts/diff_srt.py` statistics, glossary write-back, and rule capture for systematic gaps.
