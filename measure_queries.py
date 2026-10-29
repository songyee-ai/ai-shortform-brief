"""유튜브 검색어 후보 측정: 한국어 영상이 얼마나 잡히고, 얼마나 뜨고, 다른 검색어에 없는 영상을 얼마나 더하나."""
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path

import graph

WINDOW_DAYS = 7


def main():
    graph.load_env()
    now = datetime.now(graph.UTC)
    cutoff = now - timedelta(days=WINDOW_DAYS)
    base = next(s for s in graph.SOURCES if s["kind"] == "youtube")
    candidates = json.loads(Path("input/query_candidates.json").read_text(encoding="utf-8"))
    results, found = [], {}
    for c in candidates:
        src = {**base, "queries": [c["q"]], "hangul_only": False}
        try:
            rows = graph.fetch_youtube(src, cutoff)
        except Exception as exc:
            results.append({**c, "error": graph.error_label(exc)})
            continue
        ko = [r for r in rows if graph.HANGUL.search(r["title"])]
        found[c["q"]] = {r["url"] for r in ko}
        views = sorted((r["views"] for r in ko), reverse=True)
        results.append({**c, "total": len(rows), "korean": len(ko),
                        "median": int(statistics.median(views)) if views else 0, "top": views[0] if views else 0,
                        "top3": [{"title": r["title"][:80], "views": r["views"], "url": r["url"]}
                                 for r in sorted(ko, key=lambda r: -r["views"])[:3]]})
    # 지금 쓰는 4개 검색어로는 못 찾는 한국어 영상을 몇 개 더하는가
    current = set().union(*(found.get(c["q"], set()) for c in candidates if c["group"] == "현재"))
    for r in results:
        if "error" not in r:
            r["new_vs_current"] = len(found[r["q"]] - current) if r["group"] != "현재" else None

    print(f"{'검색어':<14}{'무리':<5}{'전체':>5}{'한국어':>6}{'새영상':>6}{'조회중앙값':>11}{'최고':>12}")
    print("-" * 62)
    for r in results:
        if "error" in r:
            print(f"{r['q']:<14}{r['group']:<5}  실패 {r['error']}")
            continue
        new = "-" if r["new_vs_current"] is None else r["new_vs_current"]
        print(f"{r['q']:<14}{r['group']:<5}{r['total']:>5}{r['korean']:>6}{new:>6}{r['median']:>11,}{r['top']:>12,}")
        for t in r["top3"]:
            print(f"{'':6}· {t['views']:>10,}  {t['title'][:50]}")
    out = Path("measurements") / f"queries-{now.astimezone().strftime('%Y%m%d-%H%M')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"measured_at": now.isoformat(), "window_days": WINDOW_DAYS, "results": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
