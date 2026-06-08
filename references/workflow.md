# Video Subtitler Workflow

Language scope: the rules below are written for Chinese-language videos. For
non-Chinese videos, skip the Chinese-specific steps (script normalization,
Chinese filler/connector lists) and run the generic checks with
`validate_srt.py --lang other`. For Chinese videos where the user explicitly
requests Traditional Chinese, run script checks in `--script traditional` mode
(which checks for stray Simplified characters instead) — do not skip them.

## 1. Intake

Confirm:

- source video path
- target language
- whether the user has **explicitly** asked to burn subtitles in — record it, do not
  treat the delivery form as a required question; without an explicit burn request the
  default deliverables are standalone SRT + transcript (burning is asked about at the
  end, see §10)
- whether a progress bar/module timeline is required (if yes, the first deliverable for
  it is a chapters file, see §7b)
- style preferences: font, outline, position, max line length
- any user-provided terminology list, product names, people names, course names, model names

Load the persistent glossary and merge it with user-provided terminology:

```bash
python3 scripts/glossary.py load
```

(Glossary and hallucination data live in `$VIDEO_SUBTITLER_DATA_DIR` >
`$XDG_DATA_HOME/video-subtitler` > `~/.local/share/video-subtitler/` — outside the
skill directory, so they survive skill syncs and compound across videos.)

## 2. Build fine-grained timing

Preferred path:

1. Extract audio to 16 kHz mono WAV.
2. Run ASR with word timestamps if available.
3. Build short subtitle cues from word timestamps.
4. Keep cue timing anchored to real ASR timestamps.

Forbidden shortcut:

- Do not take a coarse SRT and evenly split it into fake short cues.

### 2b. Semantic re-segmentation (highest-leverage step)

Raw cues built from audio-gap timing routinely break mid-phrase. In practice the
largest share of human fine-tuning is not fixing characters but re-cutting cues and
moving words across cue boundaries. Do a dedicated pass:

- Re-split and merge cues on linguistic boundaries: punctuation from a punctuation
  model, clause connectors (那么 / 然后 / 但是 / 所以 / 因为 / 就是), and complete
  phrases — not on silence gaps alone.
- Guarantee no cue begins or ends mid-phrase. When a word lands on the wrong side of a
  boundary, move it to the adjacent cue. After moving, set the cue boundary at the moved
  token's real start/end timestamp; preserve token order, keep cue times monotonic, and
  never display a cue earlier than the word is actually spoken.
- Keep cues short and readable (roughly one breath / one clause), but never at the cost
  of cutting a phrase in half.
- Spoken-language phrasing: within a cue, insert a space at clause/enumeration boundaries
  to match reading rhythm (e.g. "那么这是哪儿 天津 对吧"). This is formatting, not rewriting.

### 2c. Full-coverage gate (every cue, not a sample)

After re-segmentation, run:

```bash
python3 scripts/validate_srt.py DRAFT.srt --script <simplified|traditional> --json gate.json
```

- Fix every FAIL (timing/structure errors, wrong-script characters, hallucination
  phrases) and re-run.
- Review every WARNING (mid-phrase heuristics, CPS, line length, short cues) and record
  each decision in `warnings-disposition.json` in the task directory:
  `[{"id": "<warning id>", "decision": "fixed|accepted", "reason": "..."}]`
- Final acceptance is
  `validate_srt.py FINAL.srt --script <...> --dispositions warnings-disposition.json` —
  it fails while any FAIL remains or any WARNING lacks a disposition. Warning ids embed
  a text hash, so editing a cue invalidates its old disposition and forces re-review.
- Readability defaults (Chinese: CPS ≤ 9 chars/s, line ≤ 18 chars, duration ≥ 0.8 s) are
  defaults, not law — override via CLI flags when the user wants something else.
- The mid-phrase heuristics are flags for review, not verdicts; "accepted" with a reason
  is a legitimate disposition.

## 3. Conservative proofreading

ASR output is only a draft. Fix:

- obvious ASR recognition errors
- hallucinated text that does not belong to the source audio
- punctuation and casing needed for readability
- known terminology format, e.g. `AI agent`, `AI Skill`, `Excel`
- Chinese script mismatches: output Simplified Chinese by default unless the user requests Traditional
- filler words when requested

Do not:

- rewrite sentences
- summarize
- make the speaker sound more polished than they were
- delete meaningful demonstratives such as “这个环节 / 这个技能 / 这个游戏”

## 4. Hallucination and script cleanup

Mandatory before final SRT/render.

Remove or flag:

- platform hallucinations such as “请不吝点赞 / 订阅 / 转发 / 打赏 / 明镜 / 栏目” when they are not in the video
- long runs of repeated standalone filler such as “嗯” during silence
- empty or zero-duration nonsense cues
- low-confidence garbage that is semantically unrelated to neighboring transcript context

Normalize:

- Convert final Simplified Chinese deliverables to Simplified Chinese.
- Do not leave stray Traditional characters such as “這 / 門 / 課 / 讓 / 學 / 講 / 與 / 為 / 還 / 後” unless the user explicitly asks for Traditional Chinese.

Produce a cleanup report listing removed hallucinations, filler removals, and script-normalization checks.

## 5. Filler-word cleanup

Two tiers:

- **Default (subtitle deliverables):** standalone / cue-initial pure interjections
  (嗯 / 啊 / 哎 / 呃 / 哦 / 唉) carry no meaning and are the safest removal — remove them
  by default, unless the user requests a strict verbatim transcript.
- **Opt-in (only when the user requests it):** broader filler/connector cleanup such as
  这个 / 那个, 那么 / 然后, 就是 — remove conservatively.

Rules:

- Delete only when the word is discourse filler or redundant connector.
- Preserve it when it has clear reference.
- Preserve meaningful demonstratives such as 这个环节 / 这个技能 / 这个游戏.
- Produce a cleanup report with counts and examples.

## 6. Proper-noun and terminology review

Mandatory before final SRT delivery (and therefore before any rendering).

Sources:

- video topic and title
- user-provided terminology
- **slide/screen text via OCR** (see 6a) — the strongest ground truth when slides exist
- transcript context
- known tool/product/model names in the domain

### 6a. Slide OCR grounding (highest-value proper-noun source)

When the video contains slides or on-screen text, do not rely on audio + web alone:

- Extract keyframes at slide transitions (scene-change detection or fixed interval).
- OCR each slide; collect English/product/model names, people names, place names, and
  on-screen numbers into a per-video glossary.
- Cross-check ASR output against this glossary. Proper nouns and English/product/model
  names ("Kimi K2.5", "MacBook Neo", "GLM-5") are usually printed verbatim on the slide —
  fix the subtitle to match the slide spelling.
- Use the slide to disambiguate a mis-heard spoken number, then fix to what the speaker
  actually said (corroborated by the slide), not blindly to the slide's exact figure.
  Example: a slide shows 21.4%; ASR heard "百分之十"; the speaker was rounding it, so the
  fix is "百分之二十", not "百分之十" and not a forced "21.4%".
- Persist every newly verified term before the task ends — this is how the glossary
  compounds across videos. Feed JSONL to stdin:

  ```bash
  echo '{"correct": "汶上县", "wrong_variants": ["上线"], "category": "place", "source": "web", "first_seen": "2026-06-06 <video-slug>"}' \
    | python3 scripts/glossary.py add
  ```

  category ∈ product|model|person|place|course|other; source ∈ slide-ocr|user|web|retrospective.

Check:

- English words that look semantically wrong in context
- near-homophone substitutions
- **per-cue homophone semantic re-check**: ask "could any character here be a mishearing
  of a more sensible word, name, or place?" Audio + web missed local entities such as
  汶上县 (heard as 上线), 宋培彦 (as 宋培燕), 鲁棒/robust (as 鲁邦), 输入 (as 输了).
  These are examples of error classes, not fixed replacement rules.
- **people and place names: web-ground every one**; two-engine disagreement is a
  strong uncertainty signal worth a targeted re-check.
- on-screen numbers cross-checked against slide OCR
- brand/product names
- model names
- people names
- course-specific terms

Examples:

- `Trae` must not become `Tray` in AI programming context.
- `YouMind` must not become `U-Mind` / `U Mind` / `Umind`.
- `Claude` must not become `Cloud`.
- `Cursor` must not become `Curser`.

Outputs:

- corrected SRT
- corrected transcript
- term review report listing from/to/count/reason

## 7. Transcript generation

Generate a transcript from the final corrected SRT so the video, SRT, and transcript match.

## 7b. Module segmentation and chapters file (when a progress bar or chapters are requested)

When the user asks for a progress bar (or chapters), the first deliverable is the module
segmentation itself, saved in platform-ready chapter formats — not a burned-in bar.

1. Determine module boundaries from slide OCR scene changes, content/topic boundaries in
   the transcript, and any module names the user supplied.
2. Generate and validate the chapters file:

   ```bash
   printf '0:00\t导入\n2:15\t核心演示\n14:30\t总结\n' | python3 scripts/chapters.py --duration <total-seconds> --out chapters.txt
   ```

   The script enforces YouTube's official auto-chapter constraints (first chapter at
   0:00, at least 3 chapters in strictly ascending order, each at least 10 seconds) and
   emits two blocks:
   - **YouTube**: paste the block into the video description — chapters render automatically.
   - **Bilibili**: no file import exists; enter the same list manually in 创作中心(网页端)
     → 稿件 → 个性化配置 → 分段章节 (available after the video passes review and is
     public). The list also works as clickable jump timestamps in 简介/置顶评论. Follow
     whatever limits the 创作中心 UI itself shows; do not assume undocumented thresholds.
3. Deliver `chapters.txt`, then ask the user whether to burn the progress bar (and
   subtitles) into the video. Only proceed to §8 on a confirmed yes.

## 8. Rendering (opt-in, confirmation-gated)

Render only when (a) the user explicitly asked to burn upfront, or (b) the user
confirmed yes when asked after the SRT/transcript (and chapters) delivery. Never render
by default.

Use FFmpeg or equivalent.

Default subtitle visual style:

- white font
- black outline/stroke
- no large white background box
- LXGW WenKai for Chinese when available

If progress bar is enabled:

- create a reusable filter/config file
- put module labels inside bar segments
- keep module labels fixed
- render moving progress fill/head

## 9. Validation

Always (before delivering SRT/transcript):

- file existence and size check
- `validate_srt.py FINAL.srt --script <...> --dispositions warnings-disposition.json`
  must exit 0 — this covers script-form residue, known hallucination phrases (from the
  growable `hallucinations.json` library; single generic words like 订阅/转发 stay
  LLM-judged in step 4, only distinctive phrases belong in the hard-fail library),
  timing/structure errors, and full-coverage segmentation flags with dispositions
- `glossary.py check FINAL.srt transcript.md` must report zero wrong-variant hits
- grep for expected corrected terms from this task's term review report
- confirm proper nouns and on-screen numbers match the slide OCR glossary
- `chapters.py` exits 0 if a chapters file was produced

Only when rendering happened:

- ffprobe JSON report
- sample frame extraction at early/mid/late and at known terminology timestamps
- adjacent-frame extraction for progress movement if progress bar enabled

## 10. Final response

Return links to:

1. standalone SRT
2. transcript
3. chapters file, if produced (§7b)
4. processed video, only if rendering happened

If rendering has not happened and the user did not explicitly request burning upfront,
end by asking once, plainly: 是否需要把字幕（和进度条）烧录进视频？A confirmed yes
re-enters §8; otherwise the task is complete with the standalone deliverables.

Also mention any remaining limits, especially that screenshot checks do not replace a full listen-through sync check.

## 11. Retrospective (triggered, not per-task)

Trigger: the user later supplies a hand-fine-tuned version of the SRT, or explicitly
asks for a retrospective.

1. Run the rerunnable version of the v2 segmentation/recognition analysis:

   ```bash
   python3 scripts/diff_srt.py AUTO.srt FINAL_HUMAN.srt --json retro.json
   ```

   This is a statistics tool — classification boundaries are heuristic; treat the
   category split as signal, not verdict.
2. Review the from/to list; entries verified as proper-noun corrections go into the
   persistent glossary via `glossary.py add` with `"source": "retrospective"`.
3. New hallucination *phrases* (distinctive, not generic words) go into
   `hallucinations.json` in the data directory.
4. If the diff exposes a systematic rule gap (a recurring error class, not a one-off),
   follow the exemplary-editing path: update this skill's rules through the full skill
   modification workflow, so a one-off output fix becomes a permanent rule.
