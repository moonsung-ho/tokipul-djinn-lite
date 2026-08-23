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

from . import classify, config, dedupe, slack_client, sources, state


def collect_pending_feedback():
    """아직 반응을 집계하지 않은 알림의 👍/👎 개수를 세어 기록으로 남긴다.

    feedback_index.json은 지워지지 않는 누적 기록이다. 집계가 끝난 항목도
    그대로 남겨야 기록 페이지가 지난 달치까지 보여줄 수 있고, "그때 이걸
    기사감이라고 했었지" 하고 되짚어볼 수 있다. 여기서 하는 일은 목록을
    솎아내는 것이 아니라 collected 표시를 켜는 것뿐이다."""
    archive = state.load_feedback_index()
    if not archive:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    for entry in archive:
        # 이미 집계했거나 슬랙에 안 보낸 항목은 건너뛴다. 목록에서 빼지는 않는다.
        if entry.get("collected") or not entry.get("message_ts"):
            continue
        try:
            posted_at = datetime.datetime.fromisoformat(entry["posted_at_iso"])
        except (KeyError, ValueError):
            continue
        age_hours = (now - posted_at).total_seconds() / 3600
        if age_hours < config.FEEDBACK_COLLECT_AFTER_HOURS:
            continue
        try:
            counts = slack_client.get_reaction_counts(entry["channel_id"], entry["message_ts"])
        except Exception as e:
            print(f"[경고] 리액션 집계 실패 (id={entry['item_id']}): {e}")
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
        entry["collected"] = True
        entry["thumbsup"] = up
        entry["thumbsdown"] = down

    state.save_feedback_index(archive)


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

    # 같은 내용을 여러 기관이 낸 경우 한 건으로 묶는다.
    before = len(new_items)
    new_items = dedupe.group_duplicates(new_items)
    if before != len(new_items):
        print(f"중복 {before - len(new_items)}건을 묶어 {len(new_items)}건으로 정리했습니다.")

    print("AI로 취재 가치를 판단하는 중...")
    verdicts = classify.classify_items(new_items)

    feedback_index = state.load_feedback_index()
    posted_count = 0
    min_rank = config.PRIORITY_ORDER[config.MIN_PRIORITY_TO_POST]

    # 평점이 높은 것부터, 같은 점수면 최신 글부터 올린다. 등급 세 단계보다
    # 촘촘해서 같은 "중" 안에서도 볼 만한 것이 위로 온다.
    def sort_key(it):
        v = verdicts.get(it["id"]) or {}
        score = config.rating(v.get("당사자성") or v.get("priority", "중"), v.get("관심사") or "하")
        v["rating"] = score  # 알림에서 다시 계산하지 않도록 여기서 채워둔다
        return (-score, -it["date"].toordinal(), it["title"])

    new_items = sorted(new_items, key=sort_key)

    # 올릴 것이 있으면 머리말을 먼저 붙인다.
    to_post = [
        it
        for it in new_items
        if config.PRIORITY_ORDER.get((verdicts.get(it["id"]) or {}).get("priority", "중"), 1)
        >= min_rank
    ]
    if to_post:
        counts = {}
        for it in to_post:
            p = (verdicts.get(it["id"]) or {}).get("priority", "중")
            counts[p] = counts.get(p, 0) + 1
        when = datetime.date.today().strftime("%m월 %d일")
        try:
            htext, hblocks = slack_client.format_digest_header(counts, len(to_post), when)
            slack_client.post_message(htext, blocks=hblocks)
        except Exception as e:
            print(f"[경고] 머리말 전송 실패: {e}")

    for it in new_items:
        v = verdicts.get(it["id"]) or {"priority": "중", "reason": "", "entities": []}
        priority, reason = v["priority"], v.get("reason", "")
        rank = config.PRIORITY_ORDER.get(priority, 1)

        if rank >= min_rank:
            text, blocks = slack_client.format_alert(it, v)
            try:
                posted = slack_client.post_message(text, blocks=blocks)
                slack_client.add_reaction(posted["channel_id"], posted["message_ts"], "thumbsup")
                slack_client.add_reaction(posted["channel_id"], posted["message_ts"], "thumbsdown")
                feedback_index.append(
                    {
                        "item_id": it["id"],
                        "title": it["title"],
                        "url": it["url"],
                        "priority": priority,
                        "reason": reason,
                        # 아래 항목들은 웹 기록 페이지(site.py)를 만드는 데 쓰인다.
                        "source": it.get("source", ""),
                        "dept": it.get("dept") or "",
                        "date": it["date"].isoformat(),
                        "당사자성": v.get("당사자성", ""),
                        "관심사": v.get("관심사", ""),
                        "entities": v.get("entities", []),
                        "also_from": it.get("also_from", []),
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
            # 슬랙에는 안 보내지만 기록 페이지에는 남긴다. 나중에 "하로 분류했는데
            # 사실 기사감이었다"는 사례를 찾아내야 기준을 고칠 수 있기 때문이다.
            feedback_index.append(
                {
                    "item_id": it["id"],
                    "title": it["title"],
                    "url": it["url"],
                    "priority": priority,
                    "reason": reason,
                    "source": it.get("source", ""),
                    "dept": it.get("dept") or "",
                    "date": it["date"].isoformat(),
                    "당사자성": v.get("당사자성", ""),
                    "관심사": v.get("관심사", ""),
                    "entities": v.get("entities", []),
                    "also_from": it.get("also_from", []),
                    "posted_at_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "slack_skipped": True,
                    "collected": True,  # 슬랙 메시지가 없으니 반응 집계 대상에서 뺀다
                }
            )
            print(f"[슬랙 생략] ({priority}) {it['title'][:40]}")

        # 올렸든 안 올렸든, 다시 검토하지 않도록 seen에 기록한다.
        # 중복으로 묶인 문서들도 함께 기록해야 다음 실행 때 되살아나지 않는다.
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        seen[it["id"]] = now_iso
        for merged in it.get("merged_ids", []):
            seen[merged] = now_iso

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
