"""진(DJINN)-lite 설정 값 모음.

환경변수는 GitHub Actions의 Secrets/Variables에서 주입됩니다.
로컬에서 테스트할 때는 .env 파일을 만들고 `python-dotenv` 등으로 불러오거나,
셸에서 직접 export 해서 사용하세요.
"""

import os

# ── 감시 대상 게시판 ────────────────────────────────────────────
# 서울특별시교육청 공지사항 (새소식/공지 > 공지사항)
SEN_NOTICE_LIST_URL = "https://www.sen.go.kr/user/bbs/BD_selectBbsList.do?q_bbsSn=1100"
SEN_NOTICE_VIEW_URL = "https://www.sen.go.kr/user/bbs/BD_selectBbs.do?q_bbsSn=1100&q_bbsDocNo={doc_no}"

# 서울특별시교육청 보도자료 (서울교육소식 > 언론보도 > 보도자료)
SEN_PRESS_LIST_URL = "https://enews.sen.go.kr/news/list.do?step1=3&step2=1"
SEN_PRESS_VIEW_URL = "https://enews.sen.go.kr/news/view.do?bbsSn={bbs_sn}&step1=3&step2=1"

# 뉴스와이어 MY뉴스 RSS. rsskey가 개인 계정에 연결된 값이라 코드에 하드코딩하지
# 않고 환경변수로 받는다 — GitHub 저장소 Secrets에 NEWSWIRE_RSS_URL로 등록하세요.
# (공개 저장소에 키가 그대로 노출되는 것을 막기 위함. 이 값이 없으면 이 소스는
# 조용히 건너뛴다.)
NEWSWIRE_RSS_URL = os.environ.get("NEWSWIRE_RSS_URL", "")

# 대한민국 정책브리핑(korea.kr) 보도자료 — 전 부처 통합. 특정 부처만 보고 싶으면
# 아래 KOREA_KR_MINISTRY_FILTER에 부처명을 넣으세요(예: "교육부"). 비워두면 전체를
# 가져온 뒤 분류기에서 판단하게 둡니다.
KOREA_KR_PRESS_URL = "https://www.korea.kr/briefing/pressReleaseList.do"
KOREA_KR_MINISTRY_FILTER = os.environ.get("KOREA_KR_MINISTRY_FILTER", "")

# ── 수집 정책 ────────────────────────────────────────────────
# 하루 1회 실행을 기본으로 하되, 실행이 하루 정도 밀려도 놓치지 않도록
# 넉넉하게 최근 며칠치를 다시 훑고 seen.json으로 중복을 걸러냅니다.
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "3"))

# 슬랙에는 이 우선순위 이상만 올립니다. ("상", "중", "하" 중 선택)
# 지금은 분류 기준 자체를 다듬는 단계라, AI가 낮게 매긴 것도 사람이 직접
# 눈으로 훑어보고 👍/👎로 검증할 수 있도록 "하"까지 전부 올립니다.
# 나중에 feedback_log.csv가 충분히 쌓이고 분류 기준을 신뢰할 수 있게 되면
# "중"으로 올려서 절차성 공고를 자동으로 숨기는 것을 검토하세요.
MIN_PRIORITY_TO_POST = os.environ.get("MIN_PRIORITY_TO_POST", "하")
PRIORITY_ORDER = {"하": 0, "중": 1, "상": 2}

# 피드백(리액션) 수집 대상: 올린 지 이만큼 지난 메시지부터 집계합니다.
FEEDBACK_COLLECT_AFTER_HOURS = int(os.environ.get("FEEDBACK_COLLECT_AFTER_HOURS", "20"))

# ── 외부 서비스 인증 정보 ───────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# 사용할 모델은 반드시 https://docs.claude.com/en/docs/about-claude/models 에서
# 현재 제공되는 모델 ID를 확인하고 GitHub 저장소 Variables에 ANTHROPIC_MODEL로
# 등록해두세요. 분류·요약 작업이라 가장 가볍고 저렴한 모델로도 충분합니다.
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "C0BRLQBLGR3")  # #진-알림

# ── 토끼풀 취재 맥락 (분류 프롬프트에 그대로 들어갑니다) ───────────
# 2026-08-21, 편집장이 직접 판정한 268건을 근거로 작성했습니다.
# 판정 이력과 근거는 기준 문서를 참고하세요.
NEWSROOM_CONTEXT = """\
토끼풀은 서울 은평구 소재 4개 중학교 학생 32명이 자율적으로 운영하는 청소년 독립언론이다.
매달 종이신문 1000부를 4개 학교에 배포하고 웹사이트에도 기사를 올린다.

가장 중요한 전제 — 토끼풀은 학생 정책 전문지가 아니라 청소년의 눈으로 보는 종합지다.
12·3 내란 때는 호외를 발행했다. 학교와 교육 행정은 물론이고 정치, 과학, 기후, 재난,
국제 사안도 또래가 알아야 할 일이면 다룬다. 그러므로 "이 문서가 학생에게 규칙으로
적용되는가"만 물으면 안 된다. 물어야 할 것은 "또래가 이 소식을 알아야 하는가"이다.

그동안 다뤄온 주제: 중학교 학생생활규정과 인권침해, 청소년 정신건강, 기후동행카드·
K-패스처럼 청소년을 배제하는 교통·복지 정책, 학교 운영과 교육 행정의 불합리한 지점,
학교 언론의 자유(배포 금지와 압수를 직접 겪었고 시민 플랫폼 '빠띠'에 캠페인을 올린 적이
있다), 그리고 정치·사회 현안.

편집진은 은평구에 있지만 취재 범위를 은평구로 좁히지 않는다. 특정 사안이 은평구
소재인지 여부로 우선순위를 낮추지 마라. 서울 전역이든 전국이든 똑같이 다룬다.
"""

# ── 발표 주체별 우선순위 ─────────────────────────────────────
# 268건을 판정한 결과 기사감 비율이 기관마다 크게 달랐습니다. 다만 5회차 검증에서
# "비율이 0%였던 기관은 버려도 된다"는 가설이 깨졌습니다. 기사감이 없던 것은 그 기관이
# 청소년 관련 문서를 안 냈기 때문이지 기관 자체가 무관해서가 아니었습니다.
# 그래서 이 목록은 "먼저 훑을 순서"를 정하는 데만 쓰고, 버리는 근거로는 쓰지 않습니다.
HIGH_YIELD_SOURCES = [
    "교육부",            # 17건 중 12건 (71%)
    "성평등가족부",       # 4건 중 4건
    "문화체육관광부",     # 5건 중 3건
    "기후에너지환경부",   # 5건 중 3건
    "국가데이터처",       # 4건 중 2건
]
# 같은 기관이라도 게시판에 따라 성격이 완전히 다릅니다.
# 서울시교육청은 보도자료가 10건 중 7건인 반면 공지사항은 4건 중 0건이었습니다.
HIGH_YIELD_BOARDS = ["서울시교육청 보도자료"]

# ── 중복 문서 묶기 ───────────────────────────────────────────
# 같은 보도자료를 여러 부처가 각각 올리는 일이 잦습니다(예: 국립대학병원 설치법
# 시행령을 교육부와 보건복지부가 동시 게시). 제목이 이 비율 이상 겹치면 한 건으로
# 묶어 한 번만 알립니다. 5회차 검증에서 같은 내용을 나란히 보여줬을 때 판정이
# 일치했으므로, 묶어서 한 번만 묻는 편이 사람의 판정을 안정시킵니다.
DEDUPE_TITLE_SIMILARITY = float(os.environ.get("DEDUPE_TITLE_SIMILARITY", "0.86"))

# ── 개체명 표시 ──────────────────────────────────────────────
# 이트롬쇠의 진은 문서에서 인명·기관명을 뽑아 순위와 함께 보여줍니다. 논문의 예를
# 그대로 옮기면 "구역 분쟁 문서에 총리 이름이 있으면 그것만으로 뉴스 가치가 올라간다"
# 입니다. 아래 어휘는 어느 문서에나 나오므로 표시에서 제외합니다.
ENTITY_STOPWORDS = {
    "대한민국", "정부", "국무회의", "국회", "보도자료", "정책브리핑",
    "서울특별시교육청", "서울시교육청", "교육부", "행정안전부",
}
MAX_ENTITIES_SHOWN = 4
