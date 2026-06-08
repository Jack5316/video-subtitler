#!/usr/bin/env python3
"""Retrospective diff between auto-produced and human-fine-tuned SRT (stdlib).

POSITIONING: this is a retrospective *statistics* tool, the rerunnable version
of the one-off analysis that produced video-subtitler v2's "77% segmentation /
13% recognition" finding. Classification boundaries (word-moves vs text edits)
are heuristic and tolerate fuzzy cases; do NOT treat the output as a precise
judgment. The from/to list must be LLM-reviewed before entering the glossary.

Usage:
  diff_srt.py AUTO.srt FINAL.srt [--json report.json]

Categories:
  unchanged        same text (whitespace-normalized), similar timing
  boundary-change  same/merged/split content, cue boundaries moved or words
                   moved across cues (the segmentation class)
  text-change      content edited within an aligned region (recognition class);
                   from/to pairs extracted via difflib
  deletion         auto content absent from final (hallucination/filler class)
  insertion        final content absent from auto
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def parse_srt(path: Path):
    cues = []
    for bi, block in enumerate(re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()), 1):
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        m, ti = None, 0
        for i, l in enumerate(lines[:2]):
            m = TIME_RE.search(l)
            if m:
                ti = i
                break
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        cues.append({
            "n": bi,
            "start": g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000,
            "end": g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000,
            "text": re.sub(r"\s+", "", "\n".join(lines[ti + 1:])),
        })
    return cues


def overlap(a, b):
    return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def group_by_overlap(auto, final):
    """Connected components of the time-overlap bipartite graph."""
    a_links = [[] for _ in auto]
    f_links = [[] for _ in final]
    for i, a in enumerate(auto):
        for j, f in enumerate(final):
            if f["start"] >= a["end"] and overlap(a, f) == 0:
                break
            if overlap(a, f) > 0.05:
                a_links[i].append(j)
                f_links[j].append(i)
    seen_a, seen_f, groups = set(), set(), []
    for i in range(len(auto)):
        if i in seen_a:
            continue
        ga, gf = set(), set()
        stack: list = [("a", i)]
        while stack:
            kind, k = stack.pop()
            if kind == "a":
                if k in ga:
                    continue
                ga.add(k)
                stack.extend(("f", j) for j in a_links[k])
            else:
                if k in gf:
                    continue
                gf.add(k)
                stack.extend(("a", j) for j in f_links[k])
        seen_a |= ga
        seen_f |= gf
        groups.append((sorted(ga), sorted(gf)))
    for j in range(len(final)):
        if j not in seen_f:
            groups.append(([], [j]))
    return groups


def classify(auto, final):
    stats = {"unchanged": 0, "boundary-change": 0, "text-change": 0,
             "deletion": 0, "insertion": 0}
    text_changes, deletions = [], []
    for ga, gf in group_by_overlap(auto, final):
        a_text = "".join(auto[i]["text"] for i in ga)
        f_text = "".join(final[j]["text"] for j in gf)
        if not gf:
            stats["deletion"] += len(ga)
            deletions.extend(auto[i]["text"] for i in ga)
            continue
        if not ga:
            stats["insertion"] += len(gf)
            continue
        same_text = a_text == f_text
        boundary_moved = (len(ga) != len(gf)) or any(
            abs(auto[i]["start"] - final[j]["start"]) > 0.3
            or abs(auto[i]["end"] - final[j]["end"]) > 0.3
            for i, j in zip(ga, gf))
        if same_text:
            stats["boundary-change" if boundary_moved else "unchanged"] += max(len(ga), len(gf))
            continue
        ratio = difflib.SequenceMatcher(None, a_text, f_text).ratio()
        if ratio >= 0.6:
            # mostly-same content: count edited spans as text-change,
            # plus boundary-change if cue structure also moved
            sm = difflib.SequenceMatcher(None, a_text, f_text)
            pairs = [(a_text[i1:i2], f_text[j1:j2])
                     for op, i1, i2, j1, j2 in sm.get_opcodes() if op == "replace"]
            ndel = [a_text[i1:i2] for op, i1, i2, _j1, _j2 in sm.get_opcodes() if op == "delete"]
            if pairs:
                stats["text-change"] += len(pairs)
                text_changes.extend(pairs)
            if ndel:
                stats["deletion"] += len(ndel)
                deletions.extend(ndel)
            if boundary_moved:
                stats["boundary-change"] += 1
            if not pairs and not ndel and not boundary_moved:
                stats["text-change"] += 1
                text_changes.append((a_text, f_text))
        else:
            stats["text-change"] += 1
            text_changes.append((a_text, f_text))
    return stats, text_changes, deletions


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("auto_srt", type=Path)
    ap.add_argument("final_srt", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    auto, final = parse_srt(args.auto_srt), parse_srt(args.final_srt)
    stats, text_changes, deletions = classify(auto, final)
    changed_total = sum(v for k, v in stats.items() if k != "unchanged")

    print(f"== diff_srt: {args.auto_srt.name} ({len(auto)} cues) -> "
          f"{args.final_srt.name} ({len(final)} cues) ==")
    for k, v in stats.items():
        pct = f" ({100 * v / changed_total:.0f}% of changes)" \
            if changed_total and k != "unchanged" else ""
        print(f"  {k:16s} {v}{pct}")
    if text_changes:
        print("-- text changes (from -> to), LLM review required before glossary add --")
        for a, b in text_changes[:50]:
            print(f"  「{a}」 -> 「{b}」")
    if deletions:
        print("-- deletions --")
        for d in deletions[:30]:
            print(f"  「{d}」")
    if args.json:
        args.json.write_text(json.dumps(
            {"auto": str(args.auto_srt), "final": str(args.final_srt), "stats": stats,
             "text_changes": text_changes, "deletions": deletions},
            ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(0)


if __name__ == "__main__":
    main()
