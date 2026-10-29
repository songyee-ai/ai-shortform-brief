"""검수가 실제로 오류를 잡는지 일부러 틀린 요약으로 시험한다.

평소 탈락이 0건이면 검수가 일을 잘하는지, 아무것도 안 보는지 구분할 수 없다(조용한 실패).
정답을 아는 예문에 맞는 요약과 틀린 요약을 넣어, 맞는 것은 통과하고 틀린 것은 걸리는지 본다.
"""
import json
from datetime import datetime
from pathlib import Path

import graph

BODY = ("PixelForge released version 2 of its AI video generator on Monday. "
        "The update raises the maximum clip length from 6 seconds to 10 seconds and adds lip-sync for Korean and Japanese. "
        "The Pro plan costs $12 per month. There is no free tier, but new users get 20 trial credits after entering a card. "
        "The company said about 300,000 creators used version 1.")

BASE = {"section": "tools", "body": BODY, "title": "PixelForge v2", "source": "시험"}
OK = {"headline": "PixelForge 2버전, 영상 길이 10초로",
      "summary": "PixelForge가 AI 영상 생성기 2버전을 공개했습니다. 최대 길이가 6초에서 10초로 늘었고 한국어·일본어 립싱크가 추가됐습니다. "
                 "Pro 요금제는 월 12달러입니다.",
      "why": "카드를 등록하고 받는 체험 크레딧 20개로 10초 영상을 한 편 만들어 보세요."}

CASES = [   # (이름, 바꿀 칸, 기대 결과)
    ("맞는 요약", {}, True),
    ("표현만 바꿈(월 → 한 달에)", {"summary": OK["summary"].replace("월 12달러", "한 달에 12달러")}, True),
    ("숫자 틀림(10초 → 60초)", {"headline": "PixelForge 2버전, 영상 길이 60초로",
                               "summary": OK["summary"].replace("10초", "60초")}, False),
    ("없는 무료 주장(인사이트)", {"why": "무료 요금제로 오늘 10초 영상을 만들어 보세요."}, False),
    ("없는 기능(요약)", {"summary": OK["summary"] + " 4K 해상도 내보내기도 지원합니다."}, False),
    ("사용자 수 부풀림", {"summary": OK["summary"] + " 1버전 사용자는 300만 명이었습니다."}, False),
]


def main():
    graph.load_env()
    client = graph.llm()
    rows = []
    for name, change, expect in CASES:
        v = graph.check(client, {**BASE, **OK, **change})
        hit = v.ok == expect
        rows.append({"case": name, "expected_ok": expect, "got_ok": v.ok, "as_expected": hit, "problems": v.problems})
        print(f"{'○' if hit else '✗'} {name:<28} 기대={'통과' if expect else '탈락'} 결과={'통과' if v.ok else '탈락'}")
        for p in v.problems:
            print(f"      - {p}")
    score = sum(r["as_expected"] for r in rows)
    print(f"\n기대대로 {score}/{len(rows)}")
    out = Path("store") / f"verify-test-{datetime.now():%Y%m%d-%H%M}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"model": graph.MODEL, "score": f"{score}/{len(rows)}", "rows": rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
