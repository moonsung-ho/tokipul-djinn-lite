"""진(DJINN)-lite 진입점.

매일 아침 GitHub Actions가 이 스크립트를 한 번 실행합니다. 하는 일은 두 단계:

  1) 어제 이전에 슬랙에 올려둔 항목 중, 반응을 모을 만큼 시간이 지난
     것들의 👍/👎 개수를 집계해 state/feedback_log.csv에 남긴다.
  2) 감시 대상 게시판에서 새 글을 가져와 AI로 우선순위를 매기고,
     기준 이상인 것만 슬랙 #진-알림에 올린다.

실행 후에는 워크플로 파일이 state/ 아래 바뀐 파일을 그대로 커밋합니다.
"""

from __future__ import annotations

import datetime
import sys

from . import classify, config, slack_client, sources, state


def collect_pending_feedback():
    index = state.load_feedback_index()
    if not index:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    still_pending = []
    for entry in index:
        if entry.get("collected"):
            continue
        posted_at = datetime.datetime.fromisoformat(entry["posted_at_iso"])
        age_hours = (now - posted_at).total_seconds() / 3600
        if age_hours < config.FEEDBACK_COLLECT_AFTER_HOURS:
            still_pending.append(entry)
            continue
        try:
            counts = slack_client.get_reaction_counts(entry["channel_id"], entry["message_ts"])
        except Exception as e:
            print(f"[경고] 리액션 집계 실패 (id={entry['item_id']}): {e}")
            still_pending.append(entry)
            continue

        up, down = counts["thumbsup"], counts["thumbsdown"]
        if up > down:
            verdict = "기사감"
        elif down > up:
            verdict = "기사감 아님"
        else:
            verdict = "반응 없음/동률"

        state.append_feedback_log(
            {
                "item_id": entry["item_id"],
                "title": entry["title"],
                "url": entry["url"],
                "priority": entry["priority"],
                "reason": entry.get("reason", ""),
                "posted_at_iso": entry["posted_at_iso"],
                "collected_at_iso": now.isoformat(),
                "thumbsup": up,
                "thumbsdown": down,
                "verdict": verdict,
            }
        )
        print(f"[피드백 집계] {entry['title'][:40]} -> 👍{up} 👎{down} ({verdict})")
        # collected=True로 표시해두되, 목록에서 완전히 지우지 않고 남겨
        # 감사(audit) 기록으로 활용한다.
        entry["collected"] = True
        still_pending.append(entry)

    state.save_feedback_index(still_pending)


def fetch_and_classify_new_items():
    seen = state.load_seen()
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=config.LOOKBACK_DAYS)

    print("게시판을 확인하는 중...")
    all_items = sources.fetch_all(with_body=True)
    new_items = [it for it in all_items if it["id"] not in seen and it["date"] >= cutoff]

    print(f"전체 {len(all_items)}건 중 새 글 {len(new_items)}건 발견.")
    if not new_items:
        return

    print("AI로 취재 가치를 판단하는 중...")
    verdicts = classify.classify_items(new_items)

    feedback_index = state.load_feedback_index()
    posted_count = 0
    min_rank = config.PRIORITY_ORDER[config.MIN_PRIORITY_TO_POST]

    for it in new_items:
        v = verdicts.get(it["id"], {"priority": "중", "reason": ""})
        priority, reason = v["priority"], v["reason"]
        rank = config.PRIORITY_ORDER.get(priority, 1)

        if rank >= min_rank:
            text = slack_client.format_alert(it, priority, reason)
            try:
                posted = slack_client.post_message(text)
                slack_client.add_reaction(posted["channel_id"], posted["message_ts"], "thumbsup")
                slack_client.add_reaction(posted["channel_id"], posted["message_ts"], "thumbsdown")
                feedback_index.append(
                    {
                        "item_id": it["id"],
                        "title": it["title"],
                        "url": it["url"],
                        "priority": priority,
                        "reason": reason,
                        "channel_id": posted["channel_id"],
                        "message_ts": posted["message_ts"],
                        "posted_at_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "collected": False,
                    }
                )
                posted_count += 1
                print(f"[알림 전송] ({priority}) {it['title'][:40]}")
            except Exception as e:
                print(f"[오류] 슬랙 전송 실패 (id={it['id']}): {e}")
                continue
        else:
            print(f"[건너뜀] ({priority}) {it['title'][:40]}")

        # 올렸든 안 올렸든, 다시 검토하지 않도록 seen에 기록한다.
        seen[it["id"]] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    state.save_seen(seen)
    state.save_feedback_index(feedback_index)
    print(f"총 {posted_count}건을 슬랙에 올렸습니다.")


def main():
    print("=== 1단계: 지난 알림 피드백(리액션) 집계 ===")
    collect_pending_feedback()

    print("=== 2단계: 새 공고·보도자료 확인 및 알림 ===")
    fetch_and_classify_new_items()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[치명적 오류] {e}", file=sys.stderr)
        sys.exit(1)
