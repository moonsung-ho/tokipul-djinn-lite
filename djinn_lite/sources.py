"""감시 대상 게시판에서 최신 글 목록을 가져오는 부분.

지금 붙어 있는 네 소스:
  - 서울특별시교육청 공지사항 (fetch_notice_board)
  - 서울특별시교육청 보도자료 (fetch_press_releases)
  - 뉴스와이어 MY뉴스 RSS (fetch_newswire_feed) — NEWSWIRE_RSS_URL 설정 시에만
  - 대한민국 정책브리핑 korea.kr 보도자료, 전 부처 통합 (fetch_korea_kr_press)

앞의 세 소스는 자바스크립트 없이 순수 HTML(또는 RSS)로 목록이 내려오는 것을
직접 확인했습니다 (2026-08-21 기준). 다만 서울시교육청 두 게시판은 페이지네이션이
자바스크립트 함수(opMovePage 등)로 처리되어 있어 단순 GET 파라미터로는 다음
페이지를 가져올 수 없었습니다. 그래서 이 버전은 "최신 글이 보이는 첫 페이지"만
읽습니다 — 두 게시판 모두 하루 평균 1~3건 정도 올라오는 속도라 LOOKBACK_DAYS
(기본 3일) 안에서는 첫 페이지만으로 충분히 커버됩니다. 글이 갑자기 몰려서 첫
페이지 밖으로 밀려나면 놓칠 수 있으니, 만약 이 문제가 자주 발생하면
페이지네이션을 추가로 구현해야 합니다.

시도했지만 아직 못 붙인 소스: 서울시청 공식 보도자료(www.seoul.go.kr)와
교육부 보도자료(www.moe.go.kr)는 둘 다 목록이 자바스크립트로 렌더링되는 위젯
기반이라(각각 seoulboard.seoul.go.kr의 humanframe 위젯, moe.go.kr의 자체 게시판
스크립트), 단순 HTTP 요청으로는 빈 틀만 받아옵니다. 실제 데이터를 채우는
내부 API를 찾아 붙이거나 Playwright 같은 브라우저 자동화가 필요합니다. 대신
korea.kr 정책브리핑에 교육부를 포함한 모든 중앙부처 보도자료가 올라오니,
`KOREA_KR_MINISTRY_FILTER=교육부`로 설정하면 교육부만 걸러서 볼 수 있습니다
(다만 이건 중앙부처 통합 창구라 서울시청처럼 지자체 보도자료는 다루지 않습니다).

사이트 구조가 바뀌면 이 파일의 파싱 로직만 고치면 됩니다 — 나머지
모듈은 이 파일이 돌려주는 표준 딕셔너리 형태에만 의존합니다.

각 아이템의 표준 형태:
    {
        "id": "sen-notice-20260820190855051",   # seen.json 중복 체크용 고유 id
        "source": "서울시교육청 공지사항",
        "title": "...",
        "dept": "교육시설안전과" 또는 None,
        "date": datetime.date,
        "url": "https://...",
        "body_excerpt": "상세 페이지에서 뽑아온 본문 앞부분 (실패하면 빈 문자열)",
    }
"""

from __future__ import annotations

import datetime
import re

import requests
from bs4 import BeautifulSoup

from . import config

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TokipulDjinnLite/1.0; +https://tokipul.net)"}
TIMEOUT = 15


def _get(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def _fetch_body_excerpt(url: str, max_chars: int = 600) -> str:
    """상세 페이지 본문을 대략적으로 뽑아옵니다. 사이트마다 레이아웃이
    달라 완벽하지 않을 수 있어 실패해도 조용히 빈 문자열을 돌려줍니다."""
    try:
        html = _get(url)
    except Exception:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    # 본문일 가능성이 높은 영역을 넓게 잡고, 너무 짧으면 body 전체에서 뽑는다.
    candidates = soup.select(".bbs_view, .view_cont, .board_view, .cont_view, article")
    text = ""
    for c in candidates:
        t = c.get_text(" ", strip=True)
        if len(t) > len(text):
            text = t
    if len(text) < 50:
        text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def fetch_notice_board(with_body: bool = True) -> list[dict]:
    """서울특별시교육청 공지사항 게시판 (q_bbsSn=1100)."""
    html = _get(config.SEN_NOTICE_LIST_URL)
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for row in soup.select("table tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        a = row.find("a", href=True)
        if not a:
            continue
        m = re.search(r"q_bbsDocNo=(\d+)", a["href"])
        if not m:
            continue
        doc_no = m.group(1)
        title = a.get_text(" ", strip=True)
        dept = cells[1].get_text(" ", strip=True) if len(cells) > 1 else None
        date_text = cells[-2].get_text(" ", strip=True) if len(cells) >= 2 else ""
        date = _parse_date(date_text, ["%Y-%m-%d"])
        if date is None:
            continue
        url = config.SEN_NOTICE_VIEW_URL.format(doc_no=doc_no)
        items.append(
            {
                "id": f"sen-notice-{doc_no}",
                "source": "서울시교육청 공지사항",
                "title": title,
                "dept": dept,
                "date": date,
                "url": url,
                "body_excerpt": _fetch_body_excerpt(url) if with_body else "",
            }
        )
    return items


def fetch_press_releases(with_body: bool = True) -> list[dict]:
    """서울특별시교육청 보도자료 (enews.sen.go.kr, step1=3&step2=1)."""
    html = _get(config.SEN_PRESS_LIST_URL)
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_sn = set()
    for a in soup.select('a[href*="/news/view.do"]'):
        href = a["href"]
        m = re.search(r"bbsSn=(\d+)", href)
        if not m:
            continue
        bbs_sn = m.group(1)
        if bbs_sn in seen_sn:
            continue
        seen_sn.add(bbs_sn)

        # 목록 항목은 <a><strong>제목</strong><p>요약</p><div class="info">
        #   <span class="date">YYYY.MM.DD</span></div></a> 구조로 되어 있다.
        strong = a.find("strong")
        title = strong.get_text(" ", strip=True) if strong else a.get_text(" ", strip=True)
        if not title:
            continue
        p = a.find("p")
        list_excerpt = p.get_text(" ", strip=True) if p else ""

        date_span = a.select_one(".info .date")
        date_text = date_span.get_text(strip=True) if date_span else ""
        date = _parse_date(date_text, ["%Y.%m.%d"])
        if date is None:
            # 백업: 블록 전체 텍스트에서 날짜 패턴을 찾는다.
            dm = re.search(r"(20\d{2})\.(\d{2})\.(\d{2})", a.get_text(" ", strip=True))
            if dm:
                date = datetime.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
        if date is None:
            continue

        url = config.SEN_PRESS_VIEW_URL.format(bbs_sn=bbs_sn)
        body_excerpt = _fetch_body_excerpt(url) if with_body else list_excerpt
        if not body_excerpt:
            body_excerpt = list_excerpt

        items.append(
            {
                "id": f"sen-press-{bbs_sn}",
                "source": "서울시교육청 보도자료",
                "title": title,
                "dept": None,
                "date": date,
                "url": url,
                "body_excerpt": body_excerpt,
            }
        )
    return items


def _parse_date(text: str, formats: list[str]) -> datetime.date | None:
    text = text.strip()
    for fmt in formats:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def fetch_newswire_feed() -> list[dict]:
    """뉴스와이어 MY뉴스 RSS. config.NEWSWIRE_RSS_URL이 비어 있으면(설정 전)
    조용히 빈 목록을 돌려준다. RSS라 body_excerpt는 이미 목록에 포함된
    요약(description)을 그대로 쓴다 — 상세 페이지를 따로 안 가져와도 된다."""
    if not config.NEWSWIRE_RSS_URL:
        return []
    import email.utils
    import xml.etree.ElementTree as ET

    resp = requests.get(config.NEWSWIRE_RSS_URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue

        date = None
        if pub:
            try:
                date = email.utils.parsedate_to_datetime(pub).date()
            except (TypeError, ValueError):
                date = None
        if date is None:
            continue

        m = re.search(r"no=(\d+)", link)
        item_id = f"newswire-{m.group(1)}" if m else f"newswire-{abs(hash(link))}"

        items.append(
            {
                "id": item_id,
                "source": "뉴스와이어",
                "title": title,
                "dept": None,
                "date": date,
                "url": link,
                "body_excerpt": re.sub(r"\s+", " ", desc).strip()[:600],
            }
        )
    return items


def fetch_korea_kr_press(with_body: bool = True) -> list[dict]:
    """대한민국 정책브리핑(korea.kr) 보도자료 — 중앙부처 전체 통합 목록.
    config.KOREA_KR_MINISTRY_FILTER가 설정돼 있으면 그 부처 이름이 붙은
    항목만 남긴다(예: "교육부")."""
    html = _get(config.KOREA_KR_PRESS_URL)
    soup = BeautifulSoup(html, "html.parser")

    items = []
    for a in soup.select('a[href*="pressReleaseView.do"]'):
        li = a.find_parent("li")
        if li is None:
            continue
        text = li.get_text(" | ", strip=True)
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) < 3:
            continue
        title, _desc, date_text = parts[0], parts[1], parts[2]
        dept = parts[3] if len(parts) > 3 else None

        date = _parse_date(date_text, ["%Y.%m.%d"])
        if date is None:
            continue

        if config.KOREA_KR_MINISTRY_FILTER and dept != config.KOREA_KR_MINISTRY_FILTER:
            continue

        href = a["href"]
        url = href if href.startswith("http") else f"https://www.korea.kr{href}"
        m = re.search(r"newsId=(\d+)", href)
        item_id = f"korea-kr-{m.group(1)}" if m else f"korea-kr-{abs(hash(url))}"

        items.append(
            {
                "id": item_id,
                "source": f"정책브리핑({dept})" if dept else "정책브리핑",
                "title": title,
                "dept": dept,
                "date": date,
                "url": url,
                "body_excerpt": _fetch_body_excerpt(url) if with_body else "",
            }
        )
    return items


def fetch_all(with_body: bool = True) -> list[dict]:
    items = []
    items.extend(fetch_notice_board(with_body=with_body))
    items.extend(fetch_press_releases(with_body=with_body))
    items.extend(fetch_newswire_feed())
    items.extend(fetch_korea_kr_press(with_body=with_body))
    return items
