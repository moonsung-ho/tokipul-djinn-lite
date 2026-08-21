"""슬랙 Web API 최소 래퍼.

이 세션에서 만든 #진-알림 채널로 실제 자동 알림을 보내려면, 이 코드가
아니라 별도의 정식 Slack App(봇 토큰)이 필요합니다. 자세한 발급 방법은
README.md의 "슬랙 앱 만들기" 절을 참고하세요.
"""

from __future__ import annotations

import requests

from . import config

API_BASE = "https://slack.com/api"
TIMEOUT = 15


def _headers():
    if not config.SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN이 설정되어 있지 않습니다.")
    return {
        "Authorization": f"Bearer {config.SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }


def _call(method: str, payload: dict) -> dict:
    resp = requests.post(f"{API_BASE}/{method}", headers=_headers(), json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API 오류 ({method}): {data.get('error')}")
    return data


def post_message(text: str, channel_id: str | None = None, blocks: list | None = None) -> dict:
    """메시지를 올린다.

    blocks를 주면 Block Kit으로 렌더링하고, text는 알림 미리보기와 검색용
    대체 텍스트로 쓰인다. 슬랙은 blocks가 있을 때 text를 본문으로 표시하지
    않으므로 둘 다 넘겨야 알림 배너에 제목이 뜬다."""
    channel_id = channel_id or config.SLACK_CHANNEL_ID
    payload = {"channel": channel_id, "text": text, "unfurl_links": False, "unfurl_media": False}
    if blocks:
        payload["blocks"] = blocks
    data = _call("chat.postMessage", payload)
    return {"channel_id": data["channel"], "message_ts": data["ts"]}


def add_reaction(channel_id: str, message_ts: str, emoji: str) -> None:
    try:
        _call("reactions.add", {"channel": channel_id, "timestamp": message_ts, "name": emoji})
    except RuntimeError as e:
        # 이미 같은 반응이 달려 있는 경우 등은 무시해도 안전하다.
        if "already_reacted" not in str(e):
            raise


def get_reaction_counts(channel_id: str, message_ts: str) -> dict:
    """{"thumbsup": n, "thumbsdown": n} 형태로 돌려준다."""
    data = _call("reactions.get", {"channel": channel_id, "timestamp": message_ts})
    counts = {"thumbsup": 0, "thumbsdown": 0}
    for r in data.get("message", {}).get("reactions", []):
        if r["name"] in counts:
            counts[r["name"]] = r["count"]
    return counts


BADGE = {"상": "🔴", "중": "🟡", "하": "⚪"}


def _mrkdwn_escape(s: str) -> str:
    """슬랙 mrkdwn에서 특별한 뜻을 갖는 세 글자만 막는다.

    슬랙은 일반 마크다운이 아니라 자체 방언(mrkdwn)을 쓴다. 굵게는 별표 하나
    (`*굵게*`), 기울임은 밑줄(`_기울임_`), 링크는 `<주소|글자>` 꼴이다. 별표
    둘은 굵게가 되지 않는다. 공고 제목에 `<`나 `&`가 들어가면 슬랙이 태그로
    읽어버리므로 미리 바꿔둔다."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_alert(item: dict, verdict: dict) -> tuple[str, list]:
    """알림 한 건을 (대체 텍스트, Block Kit 블록) 으로 만든다.

    이트롬쇠의 진이 카드에 관련도 점수와 추출 개체명을 함께 띄우는 것을 따랐다.
    논문은 이것을 설명 가능성 장치로 본다. 점수의 근거가 보여야 기자가 AI 판단을
    검증할 수 있고, 그래야 도구를 신뢰하면서도 맹신하지 않는다.

    본문을 한 덩어리 문자열로 보내는 대신 Block Kit을 쓰는 이유는, 부가 정보를
    context 블록에 담으면 글자가 작고 흐리게 렌더링되어 제목과 판단 이유가
    먼저 눈에 들어오기 때문이다. 하루에 수십 건이 쌓이는 채널에서는 이 차이가 크다."""
    priority = verdict.get("priority", "중")
    badge = BADGE.get(priority, "⚪")
    title = _mrkdwn_escape(item["title"])
    dept = f" · {item['dept']}" if item.get("dept") else ""

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{badge} *<{item['url']}|{title}>*",
            },
        }
    ]

    # 출처 줄 — context 블록이라 작고 흐리게 나온다.
    meta = f"`{priority}`  {_mrkdwn_escape(item['source'])}{_mrkdwn_escape(dept)}  ·  {item['date'].isoformat()}"
    if item.get("also_from"):
        meta += f"  ·  🔁 {_mrkdwn_escape(', '.join(item['also_from']))}도 같은 내용을 냈습니다"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": meta}]})

    # 판단 이유 — 인용 문단으로 띄워서 AI가 한 말임을 눈에 띄게 구분한다.
    reason = verdict.get("reason", "").strip()
    if reason:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"> {_mrkdwn_escape(reason)}"},
            }
        )

    # 두 관점 점수와 개체명. 어느 관점이 등급을 끌어올렸는지 보이면
    # 기자가 판단 근거를 바로 확인할 수 있다.
    tail = []
    stake, interest = verdict.get("당사자성"), verdict.get("관심사")
    if stake and interest:
        tail.append(f"당사자성 `{stake}`  ·  또래 관심사 `{interest}`")
    if verdict.get("entities"):
        tail.append("🏷 " + _mrkdwn_escape(" · ".join(verdict["entities"])))
    if tail:
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "　|　".join(tail)}]}
        )

    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "기사감이면 :+1:, 아니면 :-1:"}],
        }
    )
    blocks.append({"type": "divider"})

    # 알림 배너와 검색에 쓰일 대체 텍스트.
    fallback = f"{badge} [{priority}] {item['title']}"
    return fallback, blocks


def format_digest_header(counts: dict, total: int, when: str) -> tuple[str, list]:
    """그날의 알림 맨 앞에 붙는 머리말. 몇 건을 어떤 등급으로 걸렀는지 한 줄로 보여준다."""
    parts = [f"{BADGE[g]} {g} *{counts.get(g, 0)}*" for g in ("상", "중", "하") if counts.get(g)]
    summary = "　　".join(parts) if parts else "새 글 없음"
    text = f"*{when} 새 공고·보도자료 {total}건*"
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": summary + "　·　우선순위 높은 순"}]},
        {"type": "divider"},
    ]
    return f"{when} 새 공고·보도자료 {total}건", blocks
