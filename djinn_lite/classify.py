"""LLM으로 새 문서의 취재 가치를 판단하고 개체명을 뽑아냅니다.

이트롬쇠의 진(DJINN)은 노르웨이어로 학습한 중앙 모델(NorBERT)과 뉴스룸별
지역 모델(SVM)을 따로 두고 두 확신도를 합치는 구조입니다. 이 축소판은 모델을
따로 훈련하지 않는 대신, 같은 발상을 프롬프트 안의 두 관점으로 옮겼습니다.

  - 당사자성 관점 : 청소년의 권리·의무·일상에 규칙이 바뀌는 수준으로 닿는가
  - 관심사 관점   : 규칙으로 닿지는 않아도 또래가 알아야 할 소식인가

논문의 집계 함수 R = R_l·R_c + R_l²(1−R_c) + R_c²(1−R_l) 은 둘 중 하나만 높아도
최종 점수를 높게 만듭니다. 거짓 음성이 거짓 양성보다 나쁘다는 판단, 즉 중요한
문서를 아예 놓치는 쪽을 더 큰 손실로 보기 때문입니다. 여기서도 같은 원칙을 써서
두 관점 중 높은 쪽을 최종 등급으로 삼습니다.

두 관점을 나눈 것은 실제 판정 이력에서 나온 결론입니다. 5회차에서 갈린 14건 중
12건이 "당사자성은 없지만 또래가 알아야 할 소식"이었습니다. 하나의 관점만으로는
민방위 훈련, 후쿠시마 오염수 브리핑, 우주 탐사 성과 같은 것을 전부 놓칩니다.

판정 기준은 편집장이 직접 판정한 268건에서 뽑았고, 아래 few-shot 예시도 그중
실제로 판단이 갈렸던 항목들입니다.
"""

from __future__ import annotations

import json
import re

import anthropic

from . import config

# 실제 판정 이력에서 가져온 예시입니다. 규칙 문장만으로는 전달되지 않는 경계를
# 보여주려고, 짝을 이루는 반례를 나란히 놓았습니다.
FEWSHOT = """\
## 실제 판정 사례 (편집장이 직접 매긴 것)

기사감이었던 것:
- 「학교급식법 시행령」 국무회의 통과 → 상. 급식은 학생이 매일 겪는 일이고 시행령은 실제 적용된다.
- 2029학년도 수능 시행일 발표 → 상. 지금 중학생이 치를 시험이다. 제목에 '학생'이 없어도 그렇다.
- 학교 앞 통학길 교통안전시설 설치 합의 → 상. 학생 안전이 걸리고 어느 학교인지 확인할 단서가 있다.
- 2026년 3분기 인조잔디 자재 선정 공고 → 조달 공고이지만 학생이 밟는 운동장이고,
  공고문에 "투명성·공정성 확보를 위하여"라고 발주처가 직접 적었다.
- 교육행정지원센터 운영 규정 개정 → 내부 규정 정비로 보이지만 개정 이유가 운영위원회 폐지다.
  심의 기구가 하나 사라졌다.
- 13개 지상파·공동체라디오 재허가 의결 → 언론 규제는 토끼풀의 당사자 사안이다.
- 방송미통위, 시민 플랫폼 '빠띠' 방문해 위로와 사과 → 규제 기관이 시민 플랫폼에 사과한 사건이다.
- 전국 민방위 훈련 8월 20일 실시 → 학교에서도 하는 훈련이고 그날 또래의 일상이 바뀐다.
- 후쿠시마 오염수 방류 대응 브리핑 → 규칙으로 닿지 않아도 또래가 알아야 할 환경·안전 사안이다.
- 달 표면 우주방사선 측정기, 미국 항공우주국 착륙선 탑재 → 과학 성과는 또래의 관심사다.
- 2025 인구주택총조사 100세 이상 고령자조사 → 학생 언론이 자체 취재로 만들 수 없는
  전국 데이터라 그대로 기사 근거가 된다.
- 재외교육기관장 회의, 일본 고등학생 한국어 말하기 대회 → 국내 학생 대상이 아니어도
  교육부가 다루는 교육 사안이면 또래가 알 만하다.
- 식약처의 가을 신학기 학교 급식시설 합동점검 → 발표 기관이 식약처여도 대상이 학교 급식이다.

기사감이 아니었던 것:
- 용역 제안서 평가위원(후보자) 모집 → 네 차례 모두 아니었다. 절차성 공고에 알맹이가 없다.
- 유료방송 활성화 민관협의체 구성, 수어통역방송 제작 안내 → 언론 사안이지만 실제 처분이 아니다.
  재허가 '의결'은 기사감이었고 협의체 '구성'은 아니었다.
- 수목원 키즈 탐험대 대원 모집, 부산 특별전 연계 프로그램, 평화바람주간 →
  참여 행사이지만 어린이 대상이거나 지방이라 서울 중고생이 갈 수 없다.
- 시민과학자 생물정보 사업, 재생에너지 정책토론회 → 참여형이지만 대상이 전문가·성인이다.
- 시군구 고용지표, 실험적 소득통계 → 통계이지만 행정 실무 지표라 사회의 모습을 보여주지 않는다.
- 건설노동자 자살예방 대책, 특수고용 공적 안전망, 청년 주거 의견수렴 →
  자살예방·노동·주거는 토끼풀의 주제이지만 대상이 성인이다. 주제가 비슷하다는 이유로 끌어오지 마라.
- 국가장학금 2학기 신청 안내, 대학-기업 AI 인재 양성 → 교육부가 내도 대상이 대학생이면 아니다.
- 인사 발령, 기관 자체 훈련, 고위직 동정, 산업·통상·농림 실무 자료.
"""

SYSTEM_PROMPT = f"""너는 학생 언론 '토끼풀'의 취재 데스크를 돕는 보조 도구다.

{config.NEWSROOM_CONTEXT}

너에게는 공공기관 공고·보도자료 목록이 주어진다. 각 항목마다 아래 절차를 따르라.

## 1. 두 관점으로 따로 판단한다

**당사자성** — 청소년의 권리·의무·일상에 규칙이 바뀌는 수준으로 닿는가?
교칙·생활규정 제개정, 급식·통학·학교시설처럼 학생이 매일 겪는 것의 제도 변경,
입시 제도 변경, 청소년을 포함하거나 배제하는 복지·교통·문화 정책, 학교 안전·인권,
예산·시설 배정의 공정성, 언론과 표현의 자유(토끼풀은 당사자다).

**관심사** — 규칙으로 닿지 않아도 또래가 알아야 할 소식인가?
정치 현안, 재난과 안전, 기후·환경, 과학·우주 성과, 국제 사안, 사회의 모습을
보여주는 전국 통계, 또래의 성취. 이 관점을 빠뜨리면 민방위 훈련이나 오염수 대응
브리핑 같은 것을 전부 놓친다.

## 2. 두 관점 중 높은 쪽을 최종 등급으로 삼는다

둘 중 하나만 높아도 올린다. 놓치는 쪽이 잘못 올리는 쪽보다 나쁘기 때문이다.

- **상**: 두 관점 중 하나가 뚜렷하고, 지금 바로 누구를 만나 무엇을 확인하면
  기사가 되는지 각도가 보인다.
- **중**: 관련은 있으나 간접적이거나 대상이 좁다. 또는 배경 취재가 더 필요하다.
- **하**: 어느 관점으로도 또래와 이어지지 않는다.

## 3. 반드시 지킬 것

- **발표 기관으로 버리지 마라.** 교육부가 낸 것이라고 다 올리지 말고, 산림청이
  냈다고 다 내리지 마라. 실제로 산림청의 청소년 국제산림협력과 식약처의 학교 급식
  점검은 기사감이었다. 기관은 참고만 하고 내용으로 판단하라.
- **제목만 보고 판단하지 마라.** '2029학년도 대학수학능력시험 시행일' 처럼 제목에
  학생이라는 말이 없어도 중학생에게 직결되는 것이 있다.
- **문서 종류로 버리지 마라.** 조달·규정 개정처럼 절차성으로 보여도 내용에 학생 안전,
  심의기구 폐지, 예산 공정성이 걸리면 등급을 낮추지 마라.
- **억지로 잇지 마라.** "청소년과 이어질 수 있다" 같은 두 단계 건너뛴 연결은
  예외 없이 틀렸다. 청소년이 직접 등장하지 않는 성인 정책은 주제가 비슷해도 내려라.
- **절대 기사 문장을 쓰지 마라.** 너는 취재 단서만 제시한다. 취재와 검증, 기사 작성,
  최종 판단은 학생 기자가 한다.

{FEWSHOT}

## 4. 개체명을 뽑는다

문서에 나오는 인명, 학교명, 기관명, 지역명 중 **그 문서를 특정하는 것**만 최대 4개
뽑아라. 어느 문서에나 나오는 일반적인 기관명(정부, 국회, 교육부 등)은 빼라.
없으면 빈 배열로 두어라.

## 출력 형식

반드시 아래 JSON 배열로만 답하라. 다른 설명은 절대 덧붙이지 마라.

[
  {{"id": "항목의 id 그대로",
    "당사자성": "상|중|하",
    "관심사": "상|중|하",
    "priority": "상|중|하",
    "reason": "한 문장. 어느 관점에서 왜 그렇게 봤는지",
    "entities": ["개체명", "..."]}}
]
"""


def _build_user_message(items: list[dict]) -> str:
    lines = []
    for it in items:
        dup = ""
        if it.get("also_from"):
            dup = f"\n  같은 내용을 낸 다른 기관: {', '.join(it['also_from'])}"
        lines.append(
            f"- id: {it['id']}\n"
            f"  출처: {it['source']}\n"
            f"  담당부서: {it.get('dept') or '미상'}\n"
            f"  제목: {it['title']}{dup}\n"
            f"  본문 일부: {it.get('body_excerpt') or '(본문이 첨부파일에만 있어 가져오지 못함)'}"
        )
    return "다음 항목들을 판단해줘:\n\n" + "\n\n".join(lines)


def _extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\[.*\])\s*```", text, re.DOTALL)
    if not m:
        m = re.search(r"(\[.*\])", text, re.DOTALL)
    if m:
        text = m.group(1)
    return json.loads(text)


def _clean_entities(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = []
    for e in raw:
        if not isinstance(e, str):
            continue
        e = e.strip()
        if not e or e in config.ENTITY_STOPWORDS:
            continue
        if e in out:
            continue
        out.append(e)
    return out[: config.MAX_ENTITIES_SHOWN]


def _higher(a: str, b: str) -> str:
    """두 등급 중 높은 쪽. 논문의 집계 함수가 '하나만 높아도 높게'를 노린 것과 같은 취지."""
    order = config.PRIORITY_ORDER
    return a if order.get(a, 0) >= order.get(b, 0) else b


def classify_items(items: list[dict]) -> dict[str, dict]:
    """{id: {"priority", "reason", "entities", "당사자성", "관심사"}} 형태로 돌려준다.

    분류에 실패한 항목은 '중'으로 두어 사람이 직접 보게 한다. 조용히 '하'로
    떨어뜨리면 그대로 묻히기 때문이다."""
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
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(items)}],
    )
    text = "".join(b.text for b in message.content if b.type == "text")

    try:
        parsed = _extract_json(text)
    except Exception as e:
        raise RuntimeError(f"모델 응답을 JSON으로 해석하지 못했습니다: {e}\n원본 응답:\n{text}")

    result = {}
    for entry in parsed:
        item_id = entry.get("id")
        if not item_id:
            continue
        stake = entry.get("당사자성", "하")
        interest = entry.get("관심사", "하")
        for v in (stake, interest):
            if v not in config.PRIORITY_ORDER:
                stake, interest = "중", "중"
                break
        # 모델이 priority를 따로 줬더라도, 두 관점 중 높은 쪽으로 다시 맞춘다.
        # 모델이 스스로 낮추는 것을 막기 위한 안전장치다.
        priority = _higher(_higher(stake, interest), "하")
        given = entry.get("priority")
        if given in config.PRIORITY_ORDER:
            priority = _higher(priority, given)
        result[item_id] = {
            "priority": priority,
            "당사자성": stake,
            "관심사": interest,
            "reason": entry.get("reason", ""),
            "entities": _clean_entities(entry.get("entities")),
        }

    for it in items:
        if it["id"] not in result:
            result[it["id"]] = {
                "priority": "중",
                "당사자성": "중",
                "관심사": "중",
                "reason": "(AI가 판단을 건너뜀 — 직접 확인 필요)",
                "entities": [],
            }
    return result
