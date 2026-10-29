"""소스 후보 측정: 본문 추출 · 최근성 · 수집 허용(robots) · 독자 관련도. 매일 돌리지 않고 채택할 때만 돌린다."""
import json
import os
import re
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import requests
import trafilatura

UA = "AI-Brief-Learning/1.0 (+RSS reader)"
HEADERS = {"User-Agent": UA}
MIN_BODY = 600      # 요약을 쓰려면 최소 이 정도 본문이 있어야 한다 (본문 기준선)
MIN_TEXT = 100      # 영상은 본문이 없으니 설명·프롬프트가 이 정도는 있어야 무엇인지 쓸 수 있다
SAMPLE = 3          # 본문 추출을 시험할 글 수
VIDEO_KINDS = ("youtube", "civitai")
TOPIC = re.compile(r"\b(video|image|animation|avatar|voice|music|3d|generat\w*|diffusion|sora|veo|runway|kling|midjourney|flux)\b"
                   r"|영상|이미지|생성|애니메이션|음성", re.I)
AI_MARK = re.compile(r"\b(ai|a\.i\.|sora|veo|kling|runway|midjourney|hailuo|pika|luma|seedance|higgsfield)\b|인공지능|생성형", re.I)
UTC = timezone.utc


def load_env(path=".env"):
    # 키는 채팅·명령 기록에 남기지 않고 .env 파일(깃에 안 올림)에서 읽는다
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def robots_ok(url):
    # True=허용, False=금지, None=확인 불가
    p = urlparse(url)
    rp = RobotFileParser()
    try:
        r = requests.get(f"{p.scheme}://{p.netloc}/robots.txt", headers=HEADERS, timeout=10)
    except requests.RequestException:
        return None
    if r.status_code == 404:
        return True      # robots.txt가 없으면 제한도 없다
    if r.status_code >= 400:
        return None
    rp.parse(r.text.splitlines())
    return rp.can_fetch(UA, url)


def iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def youtube_items(src, now):
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY 없음")
    params = {**src["params"], "part": "snippet", "type": "video", "maxResults": 50, "key": key,
              "publishedAfter": (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    r = requests.get(src["url"], params=params, timeout=20)
    r.raise_for_status()
    ids = [x["id"]["videoId"] for x in r.json().get("items", [])]
    if not ids:
        return r.status_code, []
    # 검색 결과에는 조회수가 없어서 videos 로 한 번 더 묻는다
    v = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=20,
                     params={"part": "snippet,statistics", "id": ",".join(ids), "key": key})
    v.raise_for_status()
    return r.status_code, [{"title": x["snippet"]["title"], "url": f"https://www.youtube.com/watch?v={x['id']}",
                            "summary": x["snippet"].get("description", ""), "at": iso(x["snippet"]["publishedAt"]),
                            "popularity": int(x["statistics"].get("viewCount", 0))} for x in v.json().get("items", [])]


def civitai_items(src):
    r = requests.get(src["url"], params=src["params"], headers=HEADERS, timeout=20)
    r.raise_for_status()
    rows = []
    for x in r.json().get("items", []):
        st = x.get("stats") or {}
        rows.append({"title": f"{x.get('username') or '?'} · {x.get('baseModel') or '?'}",
                     "url": f"https://civitai.com/images/{x['id']}",
                     "summary": str((x.get("meta") or {}).get("prompt") or ""), "at": iso(x["createdAt"]),
                     "popularity": sum(st.get(k, 0) for k in ("likeCount", "heartCount", "laughCount", "cryCount"))})
    return r.status_code, rows


def entries_of(src, now):
    # 소스마다 다른 모양을 title · url · at · summary 네 칸으로 맞춘다
    if src["kind"] == "youtube":
        return youtube_items(src, now)
    if src["kind"] == "civitai":
        return civitai_items(src)
    r = requests.get(src["url"], headers=HEADERS, timeout=20)
    r.raise_for_status()
    if src["kind"] == "hn":
        return r.status_code, [{"title": h.get("title") or "", "url": h.get("url") or "", "summary": "", "at": iso(h["created_at"])}
                               for h in r.json()["hits"] if h.get("url")]
    rows = []
    for e in feedparser.parse(r.content).entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        rows.append({"title": e.get("title", ""), "url": e.get("link", ""),
                     "summary": re.sub(r"<[^>]+>", "", e.get("summary", "")).strip(),
                     "at": datetime(*t[:6], tzinfo=UTC) if t else None})
    return r.status_code, rows


def body_length(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return len(trafilatura.extract(r.text) or "")
    except requests.RequestException:
        return 0


def error_label(exc):
    # 오류 문구에 요청 주소(키 포함)가 섞일 수 있어 종류와 상태 코드만 남긴다
    response = getattr(exc, "response", None)
    if isinstance(exc, RuntimeError):
        return str(exc)
    return type(exc).__name__ + (f" {response.status_code}" if response is not None else "")


def measure(src, now):
    row = {k: src.get(k) for k in ("name", "url", "kind", "lang", "tier", "section")}
    started = time.time()
    try:
        row["status"], items = entries_of(src, now)
    except Exception as exc:
        return {**row, "status": None, "error": error_label(exc), "seconds": round(time.time() - started, 1)}
    dated = [x for x in items if x["at"]]
    newest = max((x["at"] for x in dated), default=None)
    row.update(entries=len(items),
               recent_7d=sum(x["at"] >= now - timedelta(days=7) for x in dated),
               newest_hours=round((now - newest).total_seconds() / 3600) if newest else None,
               topic_ratio=round(sum(bool(TOPIC.search(x["title"] + " " + x["summary"])) for x in items) / max(len(items), 1), 2))
    if src["kind"] in VIDEO_KINDS:
        texts = [len(x["summary"]) for x in items]
        pops = [x["popularity"] for x in items]
        row.update(text_avg=sum(texts) // max(len(texts), 1),
                   text_ok=f"{sum(n >= MIN_TEXT for n in texts)}/{len(texts)}",
                   ai_mark_ratio=round(sum(bool(AI_MARK.search(x["title"] + " " + x["summary"])) for x in items) / max(len(items), 1), 2),
                   popularity_median=int(statistics.median(pops)) if pops else None,
                   popularity_top=max(pops, default=None),
                   top3=[{"title": x["title"][:80], "url": x["url"], "popularity": x["popularity"]}
                         for x in sorted(items, key=lambda x: -x["popularity"])[:3]],
                   robots="API", seconds=round(time.time() - started, 1))
        return row
    sample = [x for x in items if x["url"]][:SAMPLE]
    lengths = [body_length(x["url"]) for x in sample]
    row.update(
        rss_summary_avg=sum(len(x["summary"]) for x in items[:SAMPLE]) // max(len(items[:SAMPLE]), 1),
        body_ok=f"{sum(n >= MIN_BODY for n in lengths)}/{len(lengths)}",
        body_lengths=lengths,
        robots=robots_ok(sample[0]["url"]) if sample else None,
        seconds=round(time.time() - started, 1),
    )
    return row


def main():
    load_env()
    now = datetime.now(UTC)
    candidates = json.loads(Path("input/source_candidates.json").read_text(encoding="utf-8"))
    results = [measure(src, now) for src in candidates]

    print(f"[기사 소스] {'소스':<20}{'상태':>5}{'건수':>5}{'7일':>5}{'최신':>7}{'RSS요약':>8}{'본문':>6}{'관련도':>7}{'robots':>8}")
    print("-" * 85)
    for r in results:
        if r["kind"] in VIDEO_KINDS:
            continue
        if r.get("error"):
            print(f"{'':12}{r['name']:<20}  실패 {r['error']}")
            continue
        age = f"{r['newest_hours']}h" if r["newest_hours"] is not None else "?"
        print(f"{'':12}{r['name']:<20}{r['status']:>5}{r['entries']:>5}{r['recent_7d']:>5}{age:>7}"
              f"{r['rss_summary_avg']:>8}{r['body_ok']:>6}{r['topic_ratio']:>7}{str(r['robots']):>8}")

    print(f"\n[영상 소스] {'소스':<20}{'상태':>5}{'건수':>5}{'7일':>5}{'최신':>7}{'설명평균':>8}{'설명':>7}{'AI표시':>7}{'인기중앙값':>11}{'최고':>11}")
    print("-" * 105)
    for r in results:
        if r["kind"] not in VIDEO_KINDS:
            continue
        if r.get("error"):
            print(f"{'':12}{r['name']:<20}  실패 {r['error']}")
            continue
        age = f"{r['newest_hours']}h" if r["newest_hours"] is not None else "?"
        print(f"{'':12}{r['name']:<20}{r['status']:>5}{r['entries']:>5}{r['recent_7d']:>5}{age:>7}"
              f"{r['text_avg']:>8}{r['text_ok']:>7}{r['ai_mark_ratio']:>7}{str(r['popularity_median']):>11}{str(r['popularity_top']):>11}")
        for t in r["top3"]:
            print(f"{'':16}· {t['popularity']:>10,}  {t['title'][:50]}")

    out = Path("measurements") / f"sources-{now.astimezone().strftime('%Y%m%d-%H%M')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"measured_at": now.isoformat(), "min_body": MIN_BODY, "min_text": MIN_TEXT, "results": results},
                              ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
