"""감시 대상 게시판에서 최신 글 목록을 가져오는 부분.

두 게시판 모두 자바스크립트 없이 순수 HTML로 목록이 내려오는 것을
직접 확인했습니다 (2026-08-21 기준). 다만 페이지네이션은 두 사이트 모두
자바스크립트 함수(opMovePage 등)로 처리되어 있어 단순 GET 파라미터로는
다음 페이지를 가져올 수 없었습니다. 그래서 이 버전은 "최신 글이 보이는
첫 페이지"만 읽습니다 — 두 게시판 모두 하루 평균 1~3건 정도 올라오는
속도라 LOOKBACK_DAYS(기본 3일) 안에서는 첫 페이지만으로 충분히 커버됩니다.
글이 갑자기 몰려서 첫 페이지 밖으로 밀려나면 놓칠 수 있으니, 만약 이 문제가
자주 발생하면 페이지네이션을 추가로 구현해야 합니다.

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


def fetch_all(with_body: bool = True) -> list[dict]:
    items = []
    items.extend(fetch_notice_board(with_body=with_body))
    items.extend(fetch_press_releases(with_body=with_body))
    return items
