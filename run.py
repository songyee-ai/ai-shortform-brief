import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from graph import run

if __name__ == "__main__":          # import graph 만으로는 아무것도 실행되지 않는다
    p = argparse.ArgumentParser(description="AI 숏폼 창작자 아침 브리핑")
    p.add_argument("--hours", type=int, default=24, help="기본 수집 기간(공식 발표처는 72시간)")
    p.add_argument("--reuse", action="store_true", help="개발용: 마지막 수집 결과를 다시 써서 외부 요청·유튜브 할당량을 아낀다")
    p.add_argument("--send", action="store_true", help="Telegram에 실제로 보낸다. 없으면 미리보기만 저장(dry-run)")
    args = p.parse_args()
    out = run(args.hours, args.reuse, args.send)
    for line in out["log"]:
        print(line)
    for row in out["verified"]:     # 실행 로그만 보고도 무엇이 나갔는지 알 수 있게
        label = row.get("event") or row.get("genre")
        print(f"\n  [{row['section']}] {row['source']} [{label}] · {row['evidence_level']} · 검수 {row['verification']}")
        print(f"  ■ {row['headline']}")
        print(f"    {row['summary']}")
        print(f"    → {row['why']}")
        print(f"    {row['url']}")
    for c in out["checks"]:         # 검수에서 걸린 문제
        if not c["first_ok"]:
            print(f"\n  ✗ 검수에서 걸림: {c['source']} · {c['title'][:50]}")
            for prob in c["first_problems"]:
                print(f"      - {prob}")
            print(f"    다시 쓴 뒤: {'통과' if c.get('final_ok') else '제외'} {c.get('final_problems') or ''}")
    # 선별 근거(예선 통과·탈락, 라벨, 사유)와 검수 기록은 날짜별 파일로 남긴다
    path = Path("store/selection") / f"{datetime.now(ZoneInfo('Asia/Seoul')):%Y%m%d-%H%M}.json"   # 서버가 UTC여도 한국 시각
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**out["audit"], "checks": out["checks"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n선별·검수 근거: {path}")
    print("보낼 메시지 미리보기: store/preview-latest.txt · 실행 기록: store/metrics.jsonl")
    # 전송 실패를 정상 종료로 끝내면 예약 실행이 초록불로 남아 아무도 모른다 → 기록은 다 남긴 뒤 실패 코드로 끝낸다
    if any(line.startswith("⑤") and "전송 실패" in line for line in out["log"]):
        sys.exit(1)
