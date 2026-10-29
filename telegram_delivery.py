"""Telegram 발행: 브리핑 한 통을 HTML로 만들고 sendMessage로 보낸다. 추가 패키지·상시 서버 없음."""
import html
import os
import re
import time

import requests

LIMIT = 3900        # sendMessage 한도 4096자(UTF-16 단위)에서 여유를 둔다


def units(text):
    return len(text.encode("utf-16-le")) // 2   # 이모지는 2단위로 센다


def cut(text, n):
    return text if len(text) <= n else text[:n - 1] + "…"


def block(row):
    # 요약은 세 문장이지만 모델이 길게 쓰면 한 항목만으로 한도를 넘어 나눌 곳이 없다 → 칸마다 길이를 묶는다
    row = {**row, "summary": cut(row["summary"], 800), "why": cut(row["why"], 300), "headline": cut(row["headline"], 120)}
    e = html.escape
    if row["section"] == "trend":
        link = f'{e(row["channel"])} · 조회 {row["views"]:,}'
        head = f'<b>{e(row["headline"])}</b> [{e(row["genre"])}]'
    else:
        link, head = e(row["source"]), f'<b>{e(row["headline"])}</b>'
    return f'{head}\n{e(row["summary"])}\n👉 {e(row["why"])}\n<a href="{e(row["url"], quote=True)}">{link}</a>'


EMPTY = {"failed": "오늘은 영상을 가져오지 못했습니다(수집 실패).", "none": "오늘은 조건에 맞는 영상이 없습니다."}


def render(items, date_label, collected=0, trend_status="ok"):
    # trend_status: ok / failed(수집 자체 실패) / none(수집은 됐지만 고를 영상 없음)
    title = f"🗞️ <b>AI 숏폼 아침 브리핑 · {html.escape(date_label)}</b>"
    if not items:   # 조용한 날에도 한 통 — 멈춘 날과 구분하는 하트비트
        return [f"{title}\n\n오늘은 조용합니다. 수집 {collected}건 중 검수를 통과한 소식이 없습니다."]
    blocks = [title]
    for section, name in (("trend", "① 요즘 뜨는 AI 숏폼"), ("tools", "② 제작 도구 소식")):
        rows = [r for r in items if r["section"] == section]
        blocks.append(f"<b>{name}</b>")
        if rows:
            blocks += [block(r) for r in rows]
        else:       # 칸이 말없이 사라지면 독자는 빠진 이유를 모른다 — 독자 쪽의 조용한 실패도 막는다
            blocks.append(EMPTY["failed"] if section == "trend" and trend_status == "failed" else
                          EMPTY["none"] if section == "trend" else "오늘은 검수를 통과한 소식이 없습니다.")
    note = "모든 요약은 원문과 AI 대조 검수를 통과했습니다."
    if any(r["section"] == "trend" for r in items):
        note = "영상은 제목·설명만 보고 요약했습니다. " + note
    blocks.append(f"<i>{note}</i>")
    # 길면 항목 경계에서 나눈다(HTML 태그가 중간에 잘리지 않게)
    chunks, current = [], ""
    for b in blocks:
        joined = f"{current}\n\n{b}" if current else b
        if current and units(joined) > LIMIT:
            chunks.append(current)
            joined = b
        current = joined
    return chunks + [current]


def credentials():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token) or not re.fullmatch(r"-?\d+|@[A-Za-z0-9_]+", chat):
        raise ValueError("TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID를 확인하세요. 값은 로그에 표시하지 않습니다.")
    return token, chat


def send(chunks, session=requests):
    token, chat = credentials()
    sent = 0
    for text in chunks:
        if sent:
            time.sleep(1.1)
        try:
            response = session.post(f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}},
                timeout=(10, 25), allow_redirects=False)
            ok = response.status_code == 200 and response.json().get("ok") is True
        except (requests.RequestException, ValueError):
            # 웹훅·봇 메시지에는 중복 방지가 없다. 응답이 애매하면 다시 보내지 않고 멈춘다(토큰은 문구에 넣지 않는다)
            raise RuntimeError(f"Telegram 응답 확인 실패. 확인된 전송 {sent}개. 현재 메시지 수신 여부는 불명확하며 자동 재전송하지 않습니다.") from None
        if not ok:
            raise RuntimeError(f"Telegram 전송 실패 HTTP {response.status_code}. 확인된 전송 {sent}개. 자동 재전송하지 않습니다.") from None
        sent += 1
    return sent
