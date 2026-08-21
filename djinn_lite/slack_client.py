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


def post_message(text: str, channel_id: str | None = None) -> dict:
    channel_id = channel_id or config.SLACK_CHANNEL_ID
    data = _call("chat.postMessage", {"channel": channel_id, "text": text, "unfurl_links": False})
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


def format_alert(item: dict, priority: str, reason: str) -> str:
    badge = {"상": "🔴 우선순위 상", "중": "🟡 우선순위 중", "하": "⚪ 우선순위 하"}.get(priority, priority)
    dept = f" · {item['dept']}" if item.get("dept") else ""
    return (
        f"{badge}\n"
        f"*<{item['url']}|{item['title']}>*\n"
        f"{item['source']}{dept} · {item['date'].isoformat()}\n"
        f"💡 {reason}\n\n"
        f"기사감이면 👍, 아니면 👎로 반응해주세요."
    )
