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
NEWSROOM_CONTEXT = """\
토끼풀은 서울 은평구 소재 4개 중학교 학생 32명이 자율적으로 운영하는 청소년 독립언론이다.
매달 종이신문을 발행하고 웹사이트에도 기사를 올린다.
편집진은 은평구에 거점을 두고 있지만, 취재 범위를 은평구로 좁히지 않는다.
그동안 다뤄온 주제 자체가 서울 전역·전국 단위 정책이 많았다: 중학교 학생생활규정과
인권침해 문제, 청소년 정신건강, 기후동행카드·K-패스 등 청소년을 배제하는 교통·복지
정책, 학교 운영과 교육 행정의 불합리한 지점, 12·3 내란 같은 정치·사회 이슈(호외까지
발행한 전례가 있다). 그러니 특정 사안이 은평구 소재인지 여부로 우선순위를 낮추지 마라 —
서울시 전역 또는 전국 단위로 청소년에게 적용되는 정책이라면 지역과 무관하게 똑같이
중요하게 다뤄야 한다.
독자는 은평구 4개 중학교 학생과 학부모, 지역 주민이지만, 이들이 관심을 갖는 사안은
지역을 넘어선다.
"""
