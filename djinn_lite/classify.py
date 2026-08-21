"""LLM을 이용해 새로 올라온 공고·보도자료의 취재 가치를 판단합니다.

이트롬쇠의 진(DJINN)은 자체 훈련한 분류 모델 세 개를 쓰지만, 이 축소판은
그 대신 범용 LLM 한 번 호출로 같은 역할(우선순위 판단 + 이유 요약)을
대신합니다. 규모가 작은 뉴스룸에서는 이 정도로도 충분히 실용적입니다.
"""

from __future__ import annotations

import json
import re

import anthropic

from . import config

SYSTEM_PROMPT = f"""너는 학생 언론 '토끼풀'의 취재 데스크를 돕는 보조 도구다.
아래는 토끼풀에 대한 설명이다.

{config.NEWSROOM_CONTEXT}

너에게는 공공기관 공고·보도자료 목록이 주어진다. 각 항목에 대해
토끼풀 독자(청소년·학부모) 입장에서 취재할 가치가 있는지 판단하라.

## 판단 절차

각 항목마다 아래 세 질문에 차례로 답한 다음, 그 답을 근거로 상/중/하를 정하라.

1. **직접성**: 학생의 권리·의무·일상에 규칙이 바뀌는 수준으로 직접 영향을
   주는가? (교칙·생활규정 제개정, 청소년 대상 법령·조례 제개정과 입법예고,
   청소년을 새로 포함하거나 배제하는 복지·교통·문화 정책, 학교 안전·인권
   관련 사고나 조사, 예산·시설 배정처럼 공정성을 다툴 수 있는 사안이면 "예".
   교육청·학교 내부 행정 절차, 인사, 성과평가, 시설 자재 조달처럼 학생
   당사자에게 규칙 변화로 와닿지 않는 사안이면 "아니오".)
2. **범위**: 서울 소재 청소년 다수 또는 특정 집단 전체에 실질적으로
   해당하는 사안인가, 아니면 소수 참가자·특정 기관에 국한된 사안인가?
   (은평구 소재 여부는 범위 판단에 넣지 마라 — 서울 전역·전국 단위 정책은
   지역과 무관하게 범위가 넓은 것으로 본다.)
3. **취재 실마리**: 지금 바로 "누구를 인터뷰하고 무엇을 확인하면 기사가
   되는지" 구체적인 각도가 보이는가, 아니면 아직 막연한가?

## 등급

- **상**: 질문 1(직접성)이 뚜렷하게 "예"이고, 질문 3(취재 실마리)도 "예"인
  경우. 즉 "제도·규정이 청소년 삶을 바꾸는 사안이면서 바로 취재에 들어갈
  수 있는 것".
- **중**: 질문 1은 "예"이지만 간접적이거나 대상이 좁은 경우(특정 지원
  프로그램 참가자 수백 명 단위 등), 또는 질문 3이 아직 흐릿해서 배경
  취재가 더 필요한 경우. 통계·성과 발표성 보도자료, 신규 지원 프로그램
  소개, 학생이 지원·참가할 수 있는 기회 정보, 다른 지역 사례지만 비교
  취재에 참고할 만한 것 등이 여기 해당한다.
- **하**: 질문 1이 "아니오"에 가까운 경우. 용역·평가위원 모집, 채용공고,
  인사알림, 내부 행정규칙·성과평가 규정 개정, 시설 자재 조달, 성인·유아
  대상 프로그램처럼 청소년 당사자의 삶에 규칙 변화로 와닿지 않는 것.
  다만 "하"라고 해서 걸러내지 마라 — 지금은 분류 기준을 검증하는 단계라
  전부 목록에 포함해서 사람이 직접 훑어보게 해야 한다.

절대 기사 문장을 쓰지 마라. 너는 취재 단서만 제시할 뿐, 기사 작성과 최종
판단은 학생 기자가 한다.

반드시 아래 JSON 형식으로만 답하라. 다른 설명은 절대 덧붙이지 마라.

[
  {{"id": "항목의 id 그대로", "priority": "상|중|하", "reason": "한 문장, 왜 그렇게 판단했는지"}}
]
"""


def _build_user_message(items: list[dict]) -> str:
    lines = []
    for it in items:
        lines.append(
            f"- id: {it['id']}\n"
            f"  출처: {it['source']}\n"
            f"  담당부서: {it.get('dept') or '미상'}\n"
            f"  제목: {it['title']}\n"
            f"  본문 일부: {it.get('body_excerpt') or '(본문을 가져오지 못함)'}"
        )
    return "다음 항목들을 판단해줘:\n\n" + "\n\n".join(lines)


def _extract_json(text: str):
    text = text.strip()
    # 코드펜스로 감싸져 오는 경우 대비
    m = re.search(r"```(?:json)?\s*(\[.*\])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        m = re.search(r"(\[.*\])", text, re.DOTALL)
        if m:
            text = m.group(1)
    return json.loads(text)


def classify_items(items: list[dict]) -> dict[str, dict]:
    """{id: {"priority": "상|중|하", "reason": "..."}} 형태로 돌려준다.
    분류에 실패한 항목은 안전하게 '중'으로 두어 사람이 직접 판단하게 한다."""
    if not items:
        return {}
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")
    if not config.ANTHROPIC_MODEL:
        raise RuntimeError(
            "ANTHROPIC_MODEL이 설정되어 있지 않습니다. "
            "https://docs.claude.com/en/docs/about-claude/models 에서 "
            "현재 사용 가능한 모델 ID를 확인해 저장소 Variables에 등록하세요."
        )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(items)}],
    )
    text = "".join(block.text for block in message.content if block.type == "text")

    try:
        parsed = _extract_json(text)
    except Exception as e:
        raise RuntimeError(f"모델 응답을 JSON으로 해석하지 못했습니다: {e}\n원본 응답:\n{text}")

    result = {}
    for entry in parsed:
        item_id = entry.get("id")
        if not item_id:
            continue
        priority = entry.get("priority", "중")
        if priority not in config.PRIORITY_ORDER:
            priority = "중"
        result[item_id] = {"priority": priority, "reason": entry.get("reason", "")}

    # 모델이 빠뜨린 항목은 안전하게 '중'으로 채워 사람이 다시 볼 수 있게 한다.
    for it in items:
        if it["id"] not in result:
            result[it["id"]] = {"priority": "중", "reason": "(AI가 판단을 건너뜀 — 직접 확인 필요)"}

    return result
