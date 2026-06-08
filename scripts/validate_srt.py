#!/usr/bin/env python3
"""Full-coverage SRT quality gate for video-subtitler (pure stdlib).

All cues are checked (not spot-checked). Two severity levels:
  FAIL    — hard gate, exit non-zero (timing/structure errors, wrong script
            characters, known hallucination phrases)
  WARNING — heuristic flags (segmentation, readability) that require an LLM
            disposition entry; with --dispositions, any WARNING lacking a
            disposition also makes the gate fail.

Usage:
  validate_srt.py SUBS.srt --script simplified            # Chinese, Simplified target
  validate_srt.py SUBS.srt --script traditional           # user explicitly wants Traditional
  validate_srt.py SUBS.srt --script simplified --lang other   # non-Chinese: generic checks only
  validate_srt.py SUBS.srt --script simplified --dispositions warnings-disposition.json
  ... --json report.json --max-cps 9 --max-line-len 18 --min-duration 0.8

warnings-disposition.json format (written by the LLM after reviewing warnings):
  [{"id": "<warning id>", "decision": "fixed|accepted", "reason": "..."}]
WARNING ids embed a text hash, so a disposition goes stale (and is rejected)
if the cue text changes after it was reviewed.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# --- data dir resolution (XDG semantics) -----------------------------------

def data_dir() -> Path:
    for env, sub in (("VIDEO_SUBTITLER_DATA_DIR", ""), ("XDG_DATA_HOME", "video-subtitler")):
        v = os.environ.get(env)
        if v:
            return Path(v) / sub if sub else Path(v)
    return Path.home() / ".local" / "share" / "video-subtitler"

SEED_HALLUCINATIONS = [
    "不吝点赞", "明镜与点点", "点点栏目", "打赏支持", "订阅转发打赏",
]

def load_hallucinations() -> list:
    d = data_dir()
    f = d / "hallucinations.json"
    if not f.exists():
        d.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"phrases": SEED_HALLUCINATIONS}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("phrases", [])
    except (json.JSONDecodeError, OSError):
        print(f"[validate_srt] WARNING: cannot parse {f}, using seed list", file=sys.stderr)
        return SEED_HALLUCINATIONS

# --- script-form character sets (curated, extensible) -----------------------
# Unambiguously Traditional forms (must not appear in Simplified output):
TRADITIONAL_CHARS = set(
    "這門課讓學講與為們來時話樣裡邊應該當嗎國說讀寫聽電腦網絡機數據問題實際經驗"
    "體統設開發運測試務員觀點圖書館員過進階華語簡體繁體轉換週東西謝謝請們儘"
)
# Unambiguously Simplified forms (must not appear when user wants Traditional):
SIMPLIFIED_CHARS = set(
    "这门课让学讲为们来时话样边应该当吗国说读写听电脑网络机数据问题实际经验"
    "体统设开发运测试务员观点图书馆过进阶华语简体繁体转换周谢请尽"
)

# --- segmentation heuristics -------------------------------------------------
# Multi-char connectors that should not END a cue:
END_CONNECTORS = ["那么", "然后", "但是", "所以", "因为", "就是", "而且", "或者",
                  "以及", "还有", "比如", "如果", "虽然", "尽管"]
# Single-char prepositions/markers that rarely end a complete phrase
# (deliberately excludes 的/了/是/也/就/还 — too noisy as endings):
END_SINGLES = set("在把被对向从给和与或跟比将")
# Particles that should not BEGIN a cue (previous cue was cut too early):
BEGIN_PARTICLES = set("吗呢吧嘛呀的")

CJK_RE = re.compile(r"[一-鿿㐀-䶿]")

# --- SRT parsing -------------------------------------------------------------

TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")

def parse_srt(path: Path):
    """Return (cues, structural_errors). cue = dict(idx, start, end, text)."""
    cues, errors = [], []
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
    seen_idx = set()
    for bi, block in enumerate(blocks, 1):
        lines = [l for l in block.splitlines() if l.strip() != ""]
        if not lines:
            continue
        m, ti = None, 0
        for i, l in enumerate(lines[:2]):
            m = TIME_RE.search(l)
            if m:
                ti = i
                break
        if not m:
            errors.append(f"block {bi}: no valid timestamp line")
            continue
        idx = lines[0].strip() if ti == 1 else str(bi)
        if idx in seen_idx:
            errors.append(f"block {bi}: duplicate cue index {idx}")
        seen_idx.add(idx)
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        text = "\n".join(lines[ti + 1:]).strip()
        cues.append({"idx": idx, "n": bi, "start": start, "end": end, "text": text})
    return cues, errors

# --- checks ------------------------------------------------------------------

def wid(cue, wtype):
    h = hashlib.md5(cue["text"].encode("utf-8")).hexdigest()[:8]
    return f"{cue['n']}:{wtype}:{h}"

def check(cues, struct_errors, args):
    fails, warns = [], []
    for e in struct_errors:
        fails.append({"type": "structure", "where": e, "msg": e})

    halluc = load_hallucinations() if args.lang == "zh" else []
    prev_end = None
    for c in cues:
        dur = c["end"] - c["start"]
        loc = f"cue {c['n']} [{c['start']:.3f}-{c['end']:.3f}]"
        if not c["text"]:
            fails.append({"type": "empty-cue", "where": loc, "msg": "empty text"})
            prev_end = max(prev_end or 0, c["end"])
            continue
        if dur <= 0:
            fails.append({"type": "zero-duration", "where": loc, "msg": f"duration {dur:.3f}s"})
        if prev_end is not None and c["start"] < prev_end - 1e-3:
            fails.append({"type": "overlap", "where": loc,
                          "msg": f"starts {prev_end - c['start']:.3f}s before previous cue ends"})
        prev_end = max(prev_end or 0, c["end"])

        flat = c["text"].replace("\n", "")
        # readability (warnings)
        if dur > 0:
            cps = len(flat) / dur
            if cps > args.max_cps:
                warns.append({"id": wid(c, "cps"), "type": "cps", "where": loc,
                              "msg": f"{cps:.1f} chars/s > {args.max_cps}", "text": flat})
        if dur < args.min_duration and len(flat) > 2:
            warns.append({"id": wid(c, "short"), "type": "short-duration", "where": loc,
                          "msg": f"{dur:.3f}s < {args.min_duration}s", "text": flat})
        for line in c["text"].splitlines():
            if len(line) > args.max_line_len:
                warns.append({"id": wid(c, "linelen"), "type": "line-length", "where": loc,
                              "msg": f"line {len(line)} chars > {args.max_line_len}", "text": line})
                break

        if args.lang != "zh" or not CJK_RE.search(flat):
            continue

        # script-form consistency (hard fail)
        bad_set = TRADITIONAL_CHARS if args.script == "simplified" else SIMPLIFIED_CHARS
        label = "traditional-char" if args.script == "simplified" else "simplified-char"
        hits = sorted(set(ch for ch in flat if ch in bad_set))
        if hits:
            fails.append({"type": label, "where": loc,
                          "msg": f"unexpected {label.split('-')[0]} chars: {''.join(hits)}",
                          "text": flat})
        # hallucination phrases (hard fail)
        for ph in halluc:
            if ph and ph in flat:
                fails.append({"type": "hallucination", "where": loc,
                              "msg": f"known hallucination phrase: {ph}", "text": flat})
        # segmentation heuristics (warnings)
        stripped = flat.rstrip("。！？!?…，,、 ")
        for conn in END_CONNECTORS:
            if stripped.endswith(conn):
                warns.append({"id": wid(c, "end-conn"), "type": "ends-mid-phrase", "where": loc,
                              "msg": f"ends with connector「{conn}」", "text": flat})
                break
        else:
            if stripped and stripped[-1] in END_SINGLES:
                warns.append({"id": wid(c, "end-prep"), "type": "ends-mid-phrase", "where": loc,
                              "msg": f"ends with preposition/marker「{stripped[-1]}」", "text": flat})
        lead = flat.lstrip("。！？!?…，,、 ")
        if lead and lead[0] in BEGIN_PARTICLES and len(lead) > 1:
            warns.append({"id": wid(c, "begin-part"), "type": "begins-mid-phrase", "where": loc,
                          "msg": f"begins with particle「{lead[0]}」", "text": flat})
    return fails, warns

# --- disposition check -------------------------------------------------------

def check_dispositions(warns, path: Path):
    problems = []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        table = {e["id"]: e for e in entries if isinstance(e, dict) and "id" in e}
    except (json.JSONDecodeError, OSError, TypeError) as e:
        return [f"cannot read dispositions file {path}: {e}"]
    for w in warns:
        d = table.get(w["id"])
        if d is None:
            problems.append(f"warning {w['id']} ({w['type']} @ {w['where']}) has no disposition "
                            f"(note: ids embed a text hash; stale ids must be re-reviewed)")
        elif d.get("decision") not in ("fixed", "accepted"):
            problems.append(f"warning {w['id']}: invalid decision {d.get('decision')!r}")
        elif not d.get("reason"):
            problems.append(f"warning {w['id']}: disposition missing reason")
    return problems

# --- main --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("srt", type=Path)
    ap.add_argument("--script", required=True, choices=["simplified", "traditional"],
                    help="target Chinese script form (per user request)")
    ap.add_argument("--lang", default="zh", choices=["zh", "other"],
                    help="'other' skips Chinese-specific checks, keeps generic ones")
    ap.add_argument("--max-cps", type=float, default=None,
                    help="max chars/sec (default 9 for zh, 17 otherwise)")
    ap.add_argument("--max-line-len", type=int, default=None,
                    help="max chars per line (default 18 for zh, 42 otherwise)")
    ap.add_argument("--min-duration", type=float, default=0.8)
    ap.add_argument("--dispositions", type=Path, default=None,
                    help="warnings-disposition.json; every remaining WARNING must be covered")
    ap.add_argument("--json", type=Path, default=None, help="write machine report here")
    args = ap.parse_args()
    if args.max_cps is None:
        args.max_cps = 9.0 if args.lang == "zh" else 17.0
    if args.max_line_len is None:
        args.max_line_len = 18 if args.lang == "zh" else 42

    cues, struct_errors = parse_srt(args.srt)
    fails, warns = check(cues, struct_errors, args)
    disp_problems = check_dispositions(warns, args.dispositions) if args.dispositions else []

    report = {"file": str(args.srt), "cues": len(cues), "script": args.script,
              "lang": args.lang, "fail_count": len(fails), "warning_count": len(warns),
              "undispositioned": len(disp_problems), "fails": fails, "warnings": warns,
              "disposition_problems": disp_problems}
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"== validate_srt: {args.srt.name} | {len(cues)} cues | "
          f"script={args.script} lang={args.lang} ==")
    for f in fails:
        print(f"FAIL  [{f['type']}] {f['where']}: {f['msg']}")
    for w in warns:
        print(f"WARN  [{w['type']}] id={w['id']} {w['where']}: {w['msg']}")
    for p in disp_problems:
        print(f"UNDISPOSITIONED  {p}")
    print(f"== {len(fails)} FAIL, {len(warns)} WARNING"
          + (f", {len(disp_problems)} undispositioned" if args.dispositions else "") + " ==")

    sys.exit(1 if fails or disp_problems else 0)

if __name__ == "__main__":
    main()
