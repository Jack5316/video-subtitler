#!/usr/bin/env python3
"""Module/chapter file generator for video-subtitler (pure stdlib).

Reads chapter marks from stdin, one per line:
    <time><TAB or spaces><title>
where <time> is seconds (e.g. 90), mm:ss (1:30) or h:mm:ss (0:01:30).

Validates YouTube's official auto-chapter constraints (Help 9884579):
  - first chapter must start at 0:00
  - at least 3 chapters, strictly ascending
  - every chapter at least 10 seconds (pass --duration SECONDS to also
    validate the last chapter against total video length)

Emits a chapters.txt-style document with two blocks:
  1. YouTube — paste straight into the video description
  2. Bilibili — the same list, for manual entry in 创作中心 (per-video
     个性化配置 → 分段章节, available after the video passes review and is
     public); the list also works as clickable jump points in 简介/置顶评论

Usage:
    chapters.py [--duration 1234] [--out chapters.txt] < marks.txt
Exit non-zero on any constraint violation.
"""
import argparse
import re
import sys
from pathlib import Path

MIN_CHAPTER_SECONDS = 10
MIN_CHAPTERS = 3


def parse_time(tok: str) -> float:
    if re.fullmatch(r"\d+(\.\d+)?", tok):
        return float(tok)
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.(\d+))?", tok)
    if not m:
        raise ValueError(f"unrecognized time {tok!r} (use seconds, mm:ss or h:mm:ss)")
    h = int(m.group(1) or 0)
    frac = float(f"0.{m.group(4)}") if m.group(4) else 0.0
    return h * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + frac


def fmt_time(sec: float) -> str:
    s = int(round(sec))
    h, rem = divmod(s, 3600)
    m, ss = divmod(rem, 60)
    return f"{h}:{m:02d}:{ss:02d}" if h else f"{m}:{ss:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--duration", type=float, default=None,
                    help="total video length in seconds (validates the last chapter)")
    ap.add_argument("--out", type=Path, default=None, help="also write the document here")
    args = ap.parse_args()

    chapters, errors = [], []
    for ln, raw in enumerate(sys.stdin, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"[\t ]+", line, maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            errors.append(f"line {ln}: need '<time> <title>', got {line!r}")
            continue
        try:
            chapters.append((parse_time(parts[0]), parts[1].strip()))
        except ValueError as e:
            errors.append(f"line {ln}: {e}")

    if len(chapters) < MIN_CHAPTERS:
        errors.append(f"need at least {MIN_CHAPTERS} chapters, got {len(chapters)} "
                      "(YouTube will not render fewer)")
    if chapters and chapters[0][0] != 0:
        errors.append(f"first chapter must start at 0:00, got {fmt_time(chapters[0][0])}")
    for (t1, n1), (t2, n2) in zip(chapters, chapters[1:]):
        if t2 <= t1:
            errors.append(f"chapters must be strictly ascending: "
                          f"「{n2}」({fmt_time(t2)}) does not follow 「{n1}」({fmt_time(t1)})")
        elif t2 - t1 < MIN_CHAPTER_SECONDS:
            errors.append(f"chapter 「{n1}」 is {t2 - t1:.0f}s long "
                          f"(< {MIN_CHAPTER_SECONDS}s YouTube minimum)")
    if args.duration is not None and chapters:
        last_t, last_n = chapters[-1]
        if args.duration - last_t < MIN_CHAPTER_SECONDS:
            errors.append(f"last chapter 「{last_n}」 is {args.duration - last_t:.0f}s long "
                          f"(< {MIN_CHAPTER_SECONDS}s YouTube minimum)")
        if last_t >= args.duration:
            errors.append(f"last chapter starts at {fmt_time(last_t)}, "
                          f"beyond video end {fmt_time(args.duration)}")

    if errors:
        for e in errors:
            print(f"ERROR  {e}", file=sys.stderr)
        sys.exit(1)

    lines = ["# Chapters", "",
             "## YouTube — paste this block into the video description", ""]
    lines += [f"{fmt_time(t)} {n}" for t, n in chapters]
    lines += ["", "## Bilibili — manual entry (no file import exists)", "",
              "进入创作中心(网页端) → 稿件管理 → 该视频 → 个性化配置 → 分段章节，",
              "视频需过审且公开后才可设置。逐条录入下列时间点与标题；",
              "同一列表贴到简介或置顶评论时，时间码可点击跳转。", ""]
    lines += [f"{fmt_time(t)}  {n}" for t, n in chapters]
    doc = "\n".join(lines) + "\n"
    print(doc, end="")
    if args.out:
        args.out.write_text(doc, encoding="utf-8")


if __name__ == "__main__":
    main()
