"""알림 기록을 모아 정적 웹 페이지(docs/index.html)로 만듭니다.

화면 구성은 이트롬쇠가 실제로 쓰는 진(DJINN) 화면을 따랐습니다. 카드 하나가
가로로 세 칸입니다.

  왼쪽   평점(Rating x.xx/10)과 문서 미리보기 자리
  가운데 제목, 요약, 추출된 개체명 알약 태그
  오른쪽 상세 정보 표와 "이 사안이 기사감입니까?" 판정 버튼

평점은 config.rating()이 논문의 집계 함수로 계산합니다. 원본이 상단에 통계
숫자를 늘어놓지 않고 곧바로 필터 줄과 결과 건수만 두는 것도 그대로 따랐습니다.

읽는 것은 두 파일입니다.
  - state/feedback_index.json : 슬랙에 올린 알림의 원본 정보
  - state/feedback_log.csv    : 집계가 끝난 👍/👎 반응 결과

GitHub Actions가 매시간 실행할 때마다 다시 만들고 저장소에 커밋합니다.
GitHub Pages를 docs/ 폴더로 켜두면 그대로 웹에 반영됩니다.

    python -m djinn_lite.site              # docs/index.html 생성
    python -m djinn_lite.site --fragment   # 바깥 문서 태그 없이 본문만 출력
"""

from __future__ import annotations

import csv
import datetime
import html
import json
import os
import sys

from . import config, state

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
KST = datetime.timezone(datetime.timedelta(hours=9))

STYLE = """
/* 흰 바탕 한 가지로 통일한 화면입니다. 이트롬쇠의 진 원본이 흰 배경에 옅은
   회색 선으로만 구획을 나누는 방식이라 그대로 따랐습니다. 어두운 배색은 두지
   않되, 모든 색을 토큰으로 명시해 어떤 환경에서도 같은 화면이 나오게 합니다.
   회색은 중성 회색 대신 강조색인 초록 쪽으로 아주 살짝 기울여 두었습니다. */
:root{
  color-scheme:light;
  --bg:#FFFFFF; --surface:#FFFFFF; --surface-2:#F7F9F8; --surface-3:#FBFCFB;
  --ink:#17211D; --ink-2:#5A6560; --ink-3:#949D99;
  --line:#E4E8E5; --line-2:#F0F3F1;
  --clover:#1F6B47; --clover-soft:#EAF4EE;
  --hot:#B0452A; --hot-soft:#FBEEE9;
  --warm:#8A6714; --warm-soft:#FAF3E4;
  --radius:8px;
  --shadow:0 1px 2px rgba(23,33,29,.04);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
 font-weight:400;line-height:1.65;-webkit-font-smoothing:antialiased;font-size:15px}

/* ── 상단 막대 ───────────────────────────── */
.topbar{background:var(--bg);border-bottom:1px solid var(--line);
 padding:.85rem 0;position:sticky;top:0;z-index:30}
.topbar .in{max-width:76rem;margin:0 auto;padding:0 1.5rem;
 display:flex;align-items:center;gap:1rem}
.brand{display:flex;align-items:center;gap:.55rem;font-family:"Gowun Batang",serif;
 font-weight:700;font-size:1.15rem;letter-spacing:.02em;color:var(--ink)}
.brand svg{width:22px;height:22px;flex:none;color:var(--clover)}
.topnav{margin-left:auto;display:flex;gap:1.1rem;font-size:.82rem;color:var(--ink-2)}
.topnav a{color:inherit;text-decoration:none}
.topnav a:hover{color:var(--clover)}

/* ── 도구 줄 ────────────────────────────── */
.wrap{max-width:76rem;margin:0 auto;padding:1.5rem 1.5rem 6rem;background:var(--bg)}
.tools{display:flex;gap:.6rem;flex-wrap:wrap;align-items:flex-end;margin-bottom:1rem}
.field{display:flex;flex-direction:column;gap:.28rem}
.field label{font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);
 font-family:"IBM Plex Mono",monospace}
/* 높이를 못박아 둔다. 그냥 두면 body의 line-height 1.65가 입력칸에도 먹혀
   드롭다운보다 세로로 훨씬 커진다. 사파리가 검색칸에 덧붙이는 기본 장식도 끈다. */
select,input[type=search]{font-family:inherit;font-size:.86rem;
 height:2.2rem;padding:0 .7rem;line-height:normal;
 border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);
 color:var(--ink);-webkit-appearance:none;appearance:none}
input[type=search]::-webkit-search-decoration,
input[type=search]::-webkit-search-cancel-button{-webkit-appearance:none}
select{padding-right:1.6rem;
 background-image:linear-gradient(45deg,transparent 50%,var(--ink-3) 50%),
  linear-gradient(135deg,var(--ink-3) 50%,transparent 50%);
 background-position:calc(100% - 15px) 50%,calc(100% - 10px) 50%;
 background-size:5px 5px,5px 5px;background-repeat:no-repeat}
select:hover,input[type=search]:hover{border-color:var(--ink-3)}
select:focus-visible,input:focus-visible{outline:2px solid var(--clover);outline-offset:1px}
/* 검색칸 폭. .field가 세로 방향 flex 상자라서 여기에 flex-basis를 주면
   폭이 아니라 높이로 먹힌다. 반드시 width로 지정할 것. */
#q{width:15rem;max-width:100%}
@media (max-width:560px){ .field.grow{flex:1 1 100%} #q{width:100%} }
#q::placeholder{color:var(--ink-3)}
.chips{display:flex;gap:.3rem;flex-wrap:wrap}
.chip{font-family:inherit;font-size:.85rem;cursor:pointer;height:2.2rem;
 min-width:2.9rem;padding:0 .8rem;line-height:normal;border-radius:var(--radius);
 border:1px solid var(--line);background:var(--surface);color:var(--ink-2)}
.chip:hover{border-color:var(--ink-3);color:var(--ink)}
.chip[aria-pressed="true"]{background:var(--clover-soft);border-color:var(--clover);
 color:var(--clover);font-weight:500}
.chip:focus-visible{outline:2px solid var(--clover);outline-offset:2px}
.hits{font-size:.85rem;color:var(--ink-2);margin:.2rem 0 1rem;font-variant-numeric:tabular-nums}
.hits b{color:var(--ink);font-weight:600}

/* ── 카드 ───────────────────────────────── */
.deck{display:flex;flex-direction:column;gap:.9rem}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
 box-shadow:var(--shadow);display:grid;grid-template-columns:11rem minmax(0,1fr) 17rem;
 overflow:hidden}
.card:hover{border-color:#D6DCD8}
@media (max-width:900px){ .card{grid-template-columns:1fr} }

/* 왼쪽: 평점 */
.rate{padding:1.1rem;border-right:1px solid var(--line-2);background:var(--surface-3);
 display:flex;flex-direction:column;gap:.55rem;align-items:flex-start}
@media (max-width:900px){ .rate{border-right:0;border-bottom:1px solid var(--line-2);
 flex-direction:row;align-items:center;gap:.9rem} }
.rate .num{font-family:"IBM Plex Mono",monospace;font-size:1.55rem;font-weight:500;
 line-height:1.1;font-variant-numeric:tabular-nums;color:var(--ink)}
.rate .num s{text-decoration:none;font-size:.8rem;color:var(--ink-3)}
.rate .lab{font-family:"IBM Plex Mono",monospace;font-size:.64rem;letter-spacing:.12em;
 text-transform:uppercase;color:var(--ink-3)}
.gauge{width:100%;height:4px;background:var(--line);border-radius:99px;overflow:hidden}
@media (max-width:900px){ .gauge{width:6rem} }
.gauge i{display:block;height:100%;width:var(--w);border-radius:99px;background:var(--clover)}
.card[data-p="상"] .num{color:var(--hot)}
.card[data-p="상"] .gauge i{background:var(--hot)}
.card[data-p="중"] .num{color:var(--warm)}
.card[data-p="중"] .gauge i{background:var(--warm)}
.card[data-p="하"] .num{color:var(--ink-3)}
.card[data-p="하"] .gauge i{background:var(--ink-3)}

/* 가운데: 본문 */
.body{padding:1.1rem 1.25rem;display:flex;flex-direction:column;gap:.6rem;min-width:0;
 background:var(--surface)}
.body h2{font-family:"Gowun Batang",serif;font-weight:700;font-size:1.1rem;line-height:1.45;
 margin:0;letter-spacing:-.005em;text-wrap:balance;color:var(--ink)}
.body h2 a{color:inherit;text-decoration:none}
.body h2 a:hover{color:var(--clover);text-decoration:underline;text-underline-offset:3px}
.body h2 a:focus-visible{outline:2px solid var(--clover);outline-offset:3px;border-radius:2px}
.new{display:inline-block;font-size:.66rem;font-weight:600;color:var(--clover);
 background:var(--clover-soft);border-radius:99px;padding:.05rem .45rem;vertical-align:.15em;
 margin-left:.35rem;letter-spacing:.02em}
.body p{margin:0;font-size:.88rem;color:var(--ink-2);font-weight:300;line-height:1.7}
.pills{display:flex;gap:.3rem;flex-wrap:wrap;margin-top:.15rem}
.pill{font-size:.74rem;padding:.14rem .6rem;border-radius:99px;background:var(--surface-2);
 color:var(--ink-2);border:1px solid var(--line)}

/* 오른쪽: 상세 */
.side{padding:1.1rem 1.25rem;border-left:1px solid var(--line-2);background:var(--surface);
 display:flex;flex-direction:column;gap:.7rem;min-width:0}
@media (max-width:900px){ .side{border-left:0;border-top:1px solid var(--line-2)} }
.side h3{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);
 margin:0;font-family:"IBM Plex Mono",monospace;font-weight:400}
dl{margin:0;display:grid;grid-template-columns:4.6rem minmax(0,1fr);gap:.24rem .5rem;font-size:.78rem}
dt{color:var(--ink-3);white-space:nowrap}
dd{margin:0;color:var(--ink-2);word-break:break-word}
.ask{margin-top:auto;padding-top:.7rem;border-top:1px dashed var(--line);
 display:flex;flex-direction:column;gap:.45rem}
.ask span{font-size:.78rem;color:var(--ink-2)}
.btns{display:flex;gap:.4rem}
.btn{font-family:inherit;font-size:.8rem;padding:.35rem .85rem;border-radius:var(--radius);
 border:1px solid var(--line);background:var(--surface);color:var(--ink-2);text-decoration:none;
 display:inline-flex;align-items:center;gap:.3rem}
.btn:hover{border-color:var(--clover);color:var(--clover)}
.btn:focus-visible{outline:2px solid var(--clover);outline-offset:2px}
.done{font-size:.8rem;font-weight:500;padding:.3rem .7rem;border-radius:var(--radius);
 display:inline-block}
.done.yes{color:var(--clover);background:var(--clover-soft)}
.done.no{color:var(--hot);background:var(--hot-soft)}
.done.none{color:var(--ink-3);background:var(--surface-2)}

.empty{text-align:center;color:var(--ink-3);font-weight:300;padding:5rem 0;font-size:.92rem}
footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);
 font-family:"IBM Plex Mono",monospace;font-size:.72rem;color:var(--ink-3);line-height:1.9}
"""

SCRIPT = """
const cards = Array.from(document.querySelectorAll('.card'));
const state = {p:new Set(['상','중']), s:'전체', d:'전체', q:'', sort:'rating'};
const deck = document.getElementById('deck');

function apply(){
  const now = Date.now();
  const days = {'오늘':1,'7일':7,'30일':30}[state.d];
  cards.forEach(c => {
    const okP = state.p.has(c.dataset.p);
    const okS = state.s === '전체' || c.dataset.s === state.s;
    const okQ = !state.q || c.dataset.t.includes(state.q.toLowerCase());
    let okD = true;
    if (days) {
      const t = Date.parse(c.dataset.when);
      okD = !isNaN(t) && (now - t) <= days * 864e5;
    }
    c.hidden = !(okP && okS && okQ && okD);
  });
  const vis = cards.filter(c => !c.hidden);
  vis.sort((a,b) => state.sort === 'rating'
    ? b.dataset.r - a.dataset.r
    : Date.parse(b.dataset.when) - Date.parse(a.dataset.when));
  vis.forEach(c => deck.appendChild(c));
  document.getElementById('shown').textContent = vis.length;
  document.getElementById('empty').hidden = vis.length > 0;
}

document.querySelectorAll('[data-pf]').forEach(b => b.addEventListener('click', () => {
  const v = b.dataset.pf;
  state.p.has(v) ? state.p.delete(v) : state.p.add(v);
  b.setAttribute('aria-pressed', String(state.p.has(v)));
  apply();
}));
document.getElementById('src').addEventListener('change', e => { state.s = e.target.value; apply(); });
document.getElementById('per').addEventListener('change', e => { state.d = e.target.value; apply(); });
document.getElementById('sort').addEventListener('change', e => { state.sort = e.target.value; apply(); });
document.getElementById('q').addEventListener('input', e => { state.q = e.target.value.trim(); apply(); });
const mon = document.getElementById('mon');
if (mon) mon.addEventListener('change', e => { location.href = e.target.value; });
apply();
"""

LOGO = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M12 21v-7"/><path d="M12 14c0-2.2-1.8-4-4-4a3 3 0 1 0 0 6c2.2 0 4-.9 4-2z"/>'
    '<path d="M12 14c0-2.2 1.8-4 4-4a3 3 0 1 1 0 6c-2.2 0-4-.9-4-2z"/>'
    '<path d="M12 14c-2.2 0-4-1.8-4-4a3 3 0 1 1 6 0c0 2.2-.9 4-2 4z"/></svg>'
)


def _load_reactions() -> dict:
    out = {}
    if not os.path.exists(state.FEEDBACK_LOG_PATH):
        return out
    with open(state.FEEDBACK_LOG_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                up, down = int(row.get("thumbsup") or 0), int(row.get("thumbsdown") or 0)
            except ValueError:
                up = down = 0
            out[row["item_id"]] = {"up": up, "down": down}
    return out


def _esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _slack_link(rec: dict) -> str:
    ch, ts = rec.get("channel_id"), rec.get("message_ts")
    if not ch or not ts:
        return ""
    return f"https://{config.SLACK_WORKSPACE}.slack.com/archives/{ch}/p{str(ts).replace('.', '')}"


def _card(rec: dict, reactions: dict, now: datetime.datetime) -> str:
    p = rec.get("priority", "중")
    score = rec.get("rating")
    if score is None:
        score = config.rating(rec.get("당사자성") or p, rec.get("관심사") or "하")
    when = rec.get("posted_at_iso") or rec.get("date") or ""

    is_new = False
    try:
        t = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        is_new = (now - t).total_seconds() < 86400
    except (ValueError, AttributeError):
        pass

    src = rec.get("source", "")
    rows = [("출처", src)]
    if rec.get("dept"):
        rows.append(("발표기관", rec["dept"]))
    if rec.get("date"):
        rows.append(("게시일", rec["date"]))
    rows.append(("등급", f"{p}　·　당사자성 {rec.get('당사자성','—')} · 관심사 {rec.get('관심사','—')}"))
    if rec.get("also_from"):
        rows.append(("중복 게시", ", ".join(rec["also_from"])))
    dl = "".join(f"<dt>{_esc(k)}</dt><dd>{_esc(v)}</dd>" for k, v in rows)

    # 반응 수치는 기록 자체에 붙어 있으면 그것을 쓰고, 없으면 CSV로 보완한다.
    if rec.get("thumbsup") is not None or rec.get("thumbsdown") is not None:
        r = {"up": rec.get("thumbsup", 0), "down": rec.get("thumbsdown", 0)}
    else:
        r = reactions.get(rec.get("item_id"), {})
    link = _slack_link(rec)
    if r.get("up", 0) > r.get("down", 0):
        ask = f'<span class="done yes">기자 판정: 기사감 👍 {r["up"]}</span>'
    elif r.get("down", 0) > r.get("up", 0):
        ask = f'<span class="done no">기자 판정: 아님 👎 {r["down"]}</span>'
    elif r:
        ask = '<span class="done none">반응 없음</span>'
    elif link:
        ask = (
            "<span>이 사안이 기사감입니까?</span>"
            f'<div class="btns"><a class="btn" href="{_esc(link)}" target="_blank" '
            'rel="noopener">슬랙에서 판정하기 →</a></div>'
        )
    elif rec.get("slack_skipped"):
        ask = '<span class="done none">하 등급 · 슬랙 미발송</span>'
    else:
        ask = '<span class="done none">아직 판정 전</span>'

    pills = "".join(f'<span class="pill">{_esc(e)}</span>' for e in rec.get("entities") or [])
    searchable = f"{rec.get('title','')} {src} {rec.get('dept','')} {rec.get('reason','')}".lower()

    return f"""<article class="card" data-p="{_esc(p)}" data-s="{_esc(src)}" data-r="{score}"
 data-when="{_esc(when)}" data-t="{_esc(searchable)}">
  <div class="rate">
    <span class="lab">Rating</span>
    <span class="num">{score:.2f}<s>/10</s></span>
    <span class="gauge"><i style="--w:{min(score * 10, 100):.0f}%"></i></span>
  </div>
  <div class="body">
    <h2><a href="{_esc(rec.get('url',''))}" target="_blank" rel="noopener">{_esc(rec.get('title',''))}</a>
      {'<span class="new">새 글</span>' if is_new else ''}</h2>
    <p>{_esc(rec.get('reason',''))}</p>
    {f'<div class="pills">{pills}</div>' if pills else ''}
  </div>
  <div class="side">
    <h3>상세</h3>
    <dl>{dl}</dl>
    <div class="ask">{ask}</div>
  </div>
</article>"""


def month_of(rec: dict) -> str:
    """기록이 속한 연월(YYYY-MM). 슬랙에 올린 시각을 기준으로 한다."""
    when = (rec.get("posted_at_iso") or rec.get("date") or "")[:7]
    return when if len(when) == 7 else "날짜미상"


def build(
    records: list[dict] | None = None,
    fragment: bool = False,
    months: list[str] | None = None,
    current: str = "",
    note: str = "",
) -> str:
    """기록 한 묶음을 페이지 하나로 만든다.

    months를 주면 상단에 월별 보관 페이지로 가는 목록이 붙는다. 기록은 계속
    쌓이므로 한 페이지에 다 담으면 언젠가 열리지 않을 만큼 무거워진다. 그래서
    첫 화면에는 최근치만 싣고 나머지는 월별로 나눠 둔다."""
    if records is None:
        records = state.load_feedback_index()
    reactions = _load_reactions()
    now = datetime.datetime.now(datetime.timezone.utc)

    for rec in records:
        rec["rating"] = config.rating(
            rec.get("당사자성") or rec.get("priority", "중"), rec.get("관심사") or "하"
        )
    ordered = sorted(records, key=lambda r: -r["rating"])
    cards = "\n".join(_card(r, reactions, now) for r in ordered)
    sources = sorted({r.get("source", "") for r in records if r.get("source")})

    opts = '<option value="전체">모든 출처</option>' + "".join(
        f'<option value="{_esc(s)}">{_esc(s)}</option>' for s in sources
    )
    # "하"는 슬랙에 보내지 않는 등급이라 페이지에서도 처음엔 접어둔다.
    # 다만 목록에는 남겨서, 잘못 낮춰 분류한 사례를 찾아낼 수 있게 한다.
    chips = "".join(
        f'<button class="chip" type="button" data-pf="{g}" '
        f'aria-pressed="{"false" if g == "하" else "true"}">{g}</button>'
        for g in ("상", "중", "하")
    )
    total = len(records)
    stamp = now.astimezone(KST).strftime("%Y.%m.%d %H:%M")

    month_nav = ""
    if months:
        opts_m = ['<option value="index.html"%s>최근 기록</option>'
                  % ("" if not current else "")]
        for mm in months:
            sel = " selected" if mm == current else ""
            opts_m.append(f'<option value="{_esc(mm)}.html"{sel}>{_esc(mm)}</option>')
        month_nav = (
            '<select id="mon" aria-label="월별 기록">' + "".join(opts_m) + "</select>"
        )

    content = f"""<div class="topbar"><div class="in">
  <span class="brand">{LOGO}DJINN</span>
  <nav class="topnav">
    {month_nav}
    <a href="https://www.tokipul.net" target="_blank" rel="noopener">토끼풀</a>
  </nav>
</div></div>

<div class="wrap">
<div class="tools">
  <div class="field"><label for="per">기간</label>
    <select id="per"><option value="전체">전체</option><option value="오늘">오늘</option>
    <option value="7일">최근 7일</option><option value="30일">최근 30일</option></select></div>
  <div class="field"><label for="src">출처</label><select id="src">{opts}</select></div>
  <div class="field grow"><label for="q">검색</label>
    <input id="q" type="search" placeholder="제목·기관으로 찾기"></div>
  <div class="field"><label for="sort">정렬</label>
    <select id="sort"><option value="rating">평점 높은 순</option>
    <option value="date">최신 순</option></select></div>
  <div class="field"><label>등급</label><div class="chips">{chips}</div></div>
</div>

<p class="hits">{_esc(note)}{"" if not note else " · "}이 페이지 {total}건 중 <b id="shown">{total}</b>건 · 갱신 {stamp}</p>

<div class="deck" id="deck">
{cards}
</div>
<p class="empty" id="empty" hidden>조건에 맞는 문서가 없습니다.</p>

<footer>
  진(DJINN)-lite · 노르웨이 이트롬쇠의 Djinn 시스템을 학생 언론 규모로 옮긴 것입니다.<br>
  평점은 두 관점(당사자성·또래 관심사)을 논문의 집계 함수로 합친 값입니다.
  AI는 기사를 쓰지 않고 취재 단서만 찾습니다. 판단 이유는 틀릴 수 있으니 원문을 여세요.
</footer>
</div>
<script>{SCRIPT}</script>"""

    head = (
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        "family=Gowun+Batang:wght@400;700&family=IBM+Plex+Sans+KR:wght@300;400;500;600&"
        'family=IBM+Plex+Mono:wght@400;500&display=swap">\n'
        f"<title>진이 찾아둔 취재 단서{' · ' + current if current else ''}</title>\n"
        f"<style>{STYLE}</style>"
    )
    if fragment:
        return head + "\n" + content
    return (
        '<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="description" content="토끼풀이 공공기관 공고에서 골라낸 취재 단서 기록">\n'
        f"{head}\n</head>\n<body>\n{content}\n</body>\n</html>\n"
    )


# 첫 화면에 싣는 최근 기록 수. 넘어가는 분량은 월별 보관 페이지에서 본다.
RECENT_ON_INDEX = int(os.environ.get("RECENT_ON_INDEX", "300"))


def main():
    if "--fragment" in sys.argv:
        sys.stdout.write(build(fragment=True))
        return

    records = state.load_feedback_index()
    os.makedirs(OUT_DIR, exist_ok=True)

    # 월별로 갈라 보관 페이지를 만든다. 최신 달이 앞에 오게 정렬한다.
    by_month: dict[str, list] = {}
    for rec in records:
        by_month.setdefault(month_of(rec), []).append(rec)
    months = sorted(by_month, reverse=True)

    written = []
    for mm in months:
        page = build(
            records=by_month[mm],
            months=months,
            current=mm,
            note=f"{mm} 보관 기록",
        )
        path = os.path.join(OUT_DIR, f"{mm}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        written.append(f"{mm}.html({len(by_month[mm])}건)")

    # 첫 화면에는 최근 것만 싣는다. 전체를 한 페이지에 담으면 기록이 쌓일수록
    # 열리지 않을 만큼 무거워지기 때문이다.
    recent = sorted(
        records, key=lambda r: (r.get("posted_at_iso") or r.get("date") or ""), reverse=True
    )[:RECENT_ON_INDEX]
    note = f"전체 {len(records)}건 중 최근"
    if len(records) <= RECENT_ON_INDEX:
        note = "전체 기록"
    index = build(records=recent, months=months, current="", note=note)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index)

    print(f"index.html 생성 ({len(recent)}건 / 전체 {len(records)}건)")
    if written:
        print("월별 보관: " + ", ".join(written))


if __name__ == "__main__":
    main()
