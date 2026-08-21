"""상태 파일(state/*.json) 읽기·쓰기.

GitHub Actions는 매 실행마다 완전히 새 컨테이너에서 시작하기 때문에,
"이미 올린 글"과 "리액션 집계 대기 중인 메시지" 목록을 저장소 안의
JSON 파일로 남겨두고, 실행이 끝날 때 git commit으로 저장소에 되돌려
씁니다. 워크플로 파일(djinn-lite.yml)의 커밋 스텝과 반드시 짝을 이룹니다.
"""

import json
import os

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
SEEN_PATH = os.path.join(STATE_DIR, "seen.json")
FEEDBACK_INDEX_PATH = os.path.join(STATE_DIR, "feedback_index.json")
FEEDBACK_LOG_PATH = os.path.join(STATE_DIR, "feedback_log.csv")


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return default
        return json.loads(content)


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def load_seen():
    """{item_id: posted_iso_datetime_or_null} 형태. 슬랙에 올리지 않은
    (우선순위 낮음) 글도 다시 검토하지 않도록 여기에 함께 기록합니다."""
    return _load_json(SEEN_PATH, {})


def save_seen(seen: dict):
    _save_json(SEEN_PATH, seen)


def load_feedback_index():
    """슬랙에 올린 메시지 중 아직 리액션을 집계하지 않은 항목 목록.
    각 항목: {item_id, title, url, priority, channel_id, message_ts,
              posted_at_iso, collected: bool}"""
    return _load_json(FEEDBACK_INDEX_PATH, [])


def save_feedback_index(index: list):
    _save_json(FEEDBACK_INDEX_PATH, index)


def append_feedback_log(row: dict):
    """집계가 끝난 항목을 CSV 한 줄로 남깁니다. 나중에 분류 기준을
    다듬을 때 이 파일을 근거로 삼으면 됩니다."""
    import csv

    os.makedirs(os.path.dirname(FEEDBACK_LOG_PATH), exist_ok=True)
    is_new = not os.path.exists(FEEDBACK_LOG_PATH)
    fieldnames = [
        "item_id",
        "title",
        "url",
        "priority",
        "reason",
        "posted_at_iso",
        "collected_at_iso",
        "thumbsup",
        "thumbsdown",
        "verdict",
    ]
    with open(FEEDBACK_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
