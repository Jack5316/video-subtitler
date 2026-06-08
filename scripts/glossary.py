#!/usr/bin/env python3
"""Persistent verified glossary for video-subtitler (pure stdlib).

The glossary compounds across videos: terms verified once (via slide OCR, web
grounding, user input, or retrospective diffs) are reused in every later job.

Data dir resolution: $VIDEO_SUBTITLER_DATA_DIR > $XDG_DATA_HOME/video-subtitler
> ~/.local/share/video-subtitler. File: glossary.json.

Subcommands:
  load            print the current glossary (inject into task context at Intake)
  check SRT...    scan files for wrong_variants; exit 1 if any hit
  add             read JSONL term objects from stdin, merge by `correct`

Term object:
  {"correct": "汶上县", "wrong_variants": ["上线"], "category": "place",
   "source": "web", "first_seen": "2026-06-02 lecture-x", "notes": "..."}
category: product|model|person|place|course|other
source:   slide-ocr|user|web|retrospective
"""
import json
import os
import sys
from pathlib import Path

VALID_CATEGORIES = {"product", "model", "person", "place", "course", "other"}
VALID_SOURCES = {"slide-ocr", "user", "web", "retrospective"}


def data_dir() -> Path:
    for env, sub in (("VIDEO_SUBTITLER_DATA_DIR", ""), ("XDG_DATA_HOME", "video-subtitler")):
        v = os.environ.get(env)
        if v:
            return Path(v) / sub if sub else Path(v)
    return Path.home() / ".local" / "share" / "video-subtitler"


def glossary_path() -> Path:
    return data_dir() / "glossary.json"


def load_glossary() -> dict:
    p = glossary_path()
    if not p.exists():
        return {"terms": []}
    try:
        g = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(g.get("terms"), list):
            raise ValueError("glossary.json: 'terms' must be a list")
        return g
    except (json.JSONDecodeError, ValueError) as e:
        sys.exit(f"glossary.py: refusing to proceed, corrupt {p}: {e}")


def save_glossary(g: dict):
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    glossary_path().write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_load():
    print(json.dumps(load_glossary(), ensure_ascii=False, indent=2))


def cmd_check(paths):
    g = load_glossary()
    hits = 0
    for path in paths:
        text = Path(path).read_text(encoding="utf-8-sig")
        for t in g["terms"]:
            for wv in t.get("wrong_variants", []):
                if not wv:
                    continue
                n = text.count(wv)
                if n:
                    hits += n
                    print(f"HIT  {path}: 「{wv}」 x{n}  (should be 「{t['correct']}」, "
                          f"{t.get('category', '?')}/{t.get('source', '?')})")
    print(f"== glossary check: {hits} wrong-variant occurrence(s) in {len(paths)} file(s) ==")
    sys.exit(1 if hits else 0)


def cmd_add():
    g = load_glossary()
    by_correct = {t["correct"]: t for t in g["terms"]}
    added, merged, lineno = 0, 0, 0
    for line in sys.stdin:
        lineno += 1
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError as e:
            sys.exit(f"glossary.py add: bad JSONL at stdin line {lineno}: {e}")
        if not t.get("correct"):
            sys.exit(f"glossary.py add: line {lineno} missing 'correct'")
        if t.get("category") not in VALID_CATEGORIES:
            sys.exit(f"glossary.py add: line {lineno} category must be one of {sorted(VALID_CATEGORIES)}")
        if t.get("source") not in VALID_SOURCES:
            sys.exit(f"glossary.py add: line {lineno} source must be one of {sorted(VALID_SOURCES)}")
        t.setdefault("wrong_variants", [])
        existing = by_correct.get(t["correct"])
        if existing:
            before = set(existing.get("wrong_variants", []))
            existing["wrong_variants"] = sorted(before | set(t["wrong_variants"]))
            for k in ("category", "source", "first_seen", "notes"):
                existing.setdefault(k, t.get(k))
            merged += 1
        else:
            g["terms"].append(t)
            by_correct[t["correct"]] = t
            added += 1
    save_glossary(g)
    print(f"== glossary add: {added} new, {merged} merged; total {len(g['terms'])} terms "
          f"at {glossary_path()} ==")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("load", "check", "add"):
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "load":
        cmd_load()
    elif cmd == "check":
        if len(sys.argv) < 3:
            sys.exit("glossary.py check: need at least one file path")
        cmd_check(sys.argv[2:])
    else:
        cmd_add()


if __name__ == "__main__":
    main()
