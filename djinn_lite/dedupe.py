"""같은 내용을 여러 기관이 각각 올린 문서를 한 건으로 묶습니다.

정책브리핑에는 하나의 보도자료를 관련 부처들이 나란히 게시하는 일이 잦습니다.
실제로 「국립대학병원 설치법 시행령」 국무회의 통과는 교육부와 보건복지부가 같은
날 각각 올렸고, 불법촬영물 대응 방안은 방송미디어통신위원회와 성평등가족부가
각각 올렸습니다.

5회차 검증에서 같은 내용 두 건을 나란히 보여줬더니 판정이 일치했습니다. 반면
회차를 건너뛰어 떨어뜨려 놓았을 때는 판정이 갈렸습니다. 사람은 같은 것을 여러 번
물으면 흔들리므로, 묶어서 한 번만 묻는 편이 낫습니다. 슬랙 알림 수가 줄어드는
것은 덤입니다.

묶인 대표 항목에는 `also_from` 키로 나머지 기관 이름이 붙고, 알림에 함께
표시됩니다. "이 사안을 세 부처가 동시에 냈다"는 사실 자체가 취재 단서가 되기도
합니다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from . import config


def _normalize(title: str) -> str:
    """제목 비교용으로 다듬는다. 대괄호 말머리, 괄호 주석, 문장부호, 공백을 걷어낸다."""
    t = title
    t = re.sub(r"\[[^\]]*\]", " ", t)          # [보도자료], [참고] 등
    t = re.sub(r"\([^)]*\)", " ", t)           # (참고자료), (공동) 등
    t = re.sub(r"[「」『』…·\-—~,.'\"!?]", " ", t)
    return re.sub(r"\s+", "", t)


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def group_duplicates(items: list[dict]) -> list[dict]:
    """중복을 묶어 대표 항목만 남긴 목록을 돌려준다.

    대표는 발표 주체가 HIGH_YIELD_SOURCES에 있는 쪽을 먼저 고르고, 없으면
    본문이 가장 긴 쪽을 고른다. 본문이 길수록 판단에 쓸 정보가 많기 때문이다."""
    norm = [(_normalize(it["title"]), it) for it in items]
    used = [False] * len(norm)
    out = []

    for i, (na, a) in enumerate(norm):
        if used[i]:
            continue
        group = [a]
        used[i] = True
        for j in range(i + 1, len(norm)):
            if used[j]:
                continue
            nb, b = norm[j]
            if _similar(na, nb) >= config.DEDUPE_TITLE_SIMILARITY:
                group.append(b)
                used[j] = True

        if len(group) == 1:
            out.append(a)
            continue

        def rank(it):
            dept = it.get("dept") or ""
            src = it.get("source") or ""
            preferred = dept in config.HIGH_YIELD_SOURCES or src in config.HIGH_YIELD_BOARDS
            return (0 if preferred else 1, -len(it.get("body_excerpt") or ""))

        group.sort(key=rank)
        rep = dict(group[0])
        others = []
        for other in group[1:]:
            name = other.get("dept") or other.get("source") or ""
            if name and name != (rep.get("dept") or rep.get("source")) and name not in others:
                others.append(name)
        rep["also_from"] = others
        # 묶인 나머지 문서의 id도 들고 간다. main에서 seen.json에 함께 기록해
        # 다음 실행 때 같은 사안이 다시 올라오지 않게 하기 위함이다.
        rep["merged_ids"] = [o["id"] for o in group[1:]]
        out.append(rep)

    return out
