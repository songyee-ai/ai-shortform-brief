# AI 숏폼 아침 브리핑

AI로 숏폼 영상을 만드는 개인 창작자에게 매일 아침 Telegram으로 한 통을 보내는 LangGraph 에이전트입니다.

- **① 요즘 뜨는 AI 숏폼**: 지난 7일 동안 조회수가 오른 한국어 AI 영상 2편 (YouTube Data API)
- **② 제작 도구 소식**: 바로 써 볼 수 있는 AI 영상·이미지 도구 소식 3건 (공식 블로그 RSS, 기술 매체 RSS, Hacker News 검색 API)

항목마다 헤드라인, 원문만 근거로 쓴 요약, "오늘 해 볼 행동 하나"가 붙습니다. 요약은 원문과 대조하는 별도 검수를 통과해야 나갑니다.

설계와 실행 기록은 [REPORT.md](REPORT.md)에 있습니다.

## 구조

```
collect → select → report(항목마다 병렬) → verify → publish
```

| 파일 | 역할 |
|---|---|
| `graph.py` | 다섯 노드와 그래프 |
| `run.py` | 실행 진입점. 로그를 출력하고 선별·검수 근거를 `store/selection/`에 저장 |
| `audience.yaml` | 독자, 중요도 기준, 제외 조건, 영상 자리 규칙, 하루 발행 수 |
| `telegram_delivery.py` | 메시지 렌더링(HTML)과 전송 |
| `store/metrics.jsonl` | 실행마다 단계별 건수, 검수 결과, 전송 상태 한 줄 |
| `store/sent.jsonl` | 보낸 주소. 다음 날 같은 소식을 다시 보내지 않게 |
| `measure_sources.py`, `measure_queries.py` | 소스 후보와 유튜브 검색어 후보 측정 (`measurements/`) |
| `check_verify.py` | 일부러 틀린 요약을 넣어 검수가 잡는지 확인 |

## 로컬 실행

Python 3.12 기준입니다.

```bash
pip install -r requirements.txt
```

프로젝트 폴더에 `.env`를 만들고 키 네 개를 넣습니다. `.env`는 깃에 올라가지 않습니다.

```
YOUTUBE_API_KEY=...
OPENAI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

```bash
python run.py
```

기본은 보내지 않고 `store/preview-latest.txt`에 미리보기만 남깁니다. 실제로 보내려면 `--send`를 붙입니다. 개발 중에는 `--reuse`로 마지막 수집 결과를 다시 써서 외부 요청과 유튜브 할당량을 아낍니다.

## 매일 자동 실행

`.github/workflows/daily-brief.yml`이 매일 한국 시간 07:30에 `run.py --send`를 실행하고, 보낸 목록과 실행 기록을 저장소에 다시 커밋합니다. 저장소 Settings → Secrets and variables → Actions에 위 키 네 개를 같은 이름으로 등록해야 합니다. 전송이 실패하면 기록은 남기고 실행은 실패로 끝나서 GitHub 알림으로 알 수 있습니다.
