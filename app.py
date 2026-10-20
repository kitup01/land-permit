import altair as alt
import pandas as pd
import streamlit as st
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import collect  # 같은 폴더의 수집 코드 재사용 (사이트 요청 방식 동일)

st.set_page_config(page_title="토지거래허가 현황", page_icon="🏠", layout="wide")

st.markdown("""
<style>
    .block-container {padding-top: 5rem; max-width: 1200px;}   /* 상단 바에 가리지 않도록 여백 확보 */
    .hero {display: flex; align-items: center; gap: 14px; margin-bottom: 1.4rem;}
    .hero-icon {font-size: 2.2rem; background: linear-gradient(135deg, #14b8a6, #0d9488);
                width: 58px; height: 58px; border-radius: 16px; display: flex;
                align-items: center; justify-content: center; box-shadow: 0 4px 12px rgba(13,148,136,.25);}
    .hero-title {font-size: 1.8rem; font-weight: 800; color: #0f172a; line-height: 1.2;}
    .hero-sub {color: #64748b; font-size: .92rem; margin-top: 2px;}
    .kpi {background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px;
          padding: 18px 20px; height: 100%; box-shadow: 0 1px 3px rgba(15,23,42,.05);}
    .kpi-head {display: flex; justify-content: space-between; align-items: flex-start;}
    .kpi-label {color: #64748b; font-size: .85rem; font-weight: 600;}
    .kpi-icon {width: 38px; height: 38px; border-radius: 12px; background: #f0fdfa;
               display: flex; align-items: center; justify-content: center; font-size: 1.1rem;}
    .kpi-value {color: #0f172a; font-size: 1.7rem; font-weight: 800; margin-top: 8px;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
    .kpi-unit {font-size: .95rem; font-weight: 600; color: #475569; margin-left: 4px;}
    .kpi-sub {color: #64748b; font-size: .85rem; margin-top: 4px;}
    .up {color: #dc2626; font-weight: 600;}
    .down {color: #2563eb; font-weight: 600;}
    .period {display: inline-block; background: #f1f5f9; color: #334155; font-size: .9rem;
             padding: 6px 14px; border-radius: 999px; margin: 1rem 0 .8rem;}
    .section-title {font-weight: 700; color: #0f172a; font-size: 1.05rem; margin-bottom: .3rem;}
    .empty {text-align: center; padding: 70px 20px; color: #64748b; font-size: 1rem;
            background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 16px;}
    @media (max-width: 640px) {
        .block-container {padding: 4.5rem .75rem 1rem;}
        .hero-title {font-size: 1.4rem;}
        .hero-icon {width: 46px; height: 46px; font-size: 1.6rem;}
        .kpi {padding: 14px 16px;}
        .kpi-value {font-size: 1.4rem;}
        .kpi-icon {width: 32px; height: 32px; font-size: 1rem;}
        .period {font-size: .8rem;}
    }
</style>
""", unsafe_allow_html=True)

CSV = Path(__file__).parent / "permits.csv"
PLACEHOLDER_GU = "자치구 선택"

if not CSV.exists():
    st.error("permits.csv 파일이 없습니다. 먼저 데이터 파일을 넣어주세요.")
    st.stop()


class FetchFailed(Exception):
    pass


@st.cache_data(ttl=600)
def load():
    df = pd.read_csv(CSV, dtype=str)
    df["허가일자"] = pd.to_datetime(df["허가일자"])
    return df


APT_CSV = Path(__file__).parent / "apartment_names.csv"


@st.cache_resource
def load_apartment_info():
    """지번 주소 → (세대 수, 사용승인 연도) (단지 식별정보 기반). 튜플로 가볍게 보관"""
    if not APT_CSV.exists():
        return {}
    m = pd.read_csv(APT_CSV, dtype=str, encoding="utf-8-sig")
    # 열 순서: 주소, 아파트명, 세대수, 사용승인연도
    return {r[0]: (r[2], r[3]) for r in m.itertuples(index=False)}


@st.cache_resource
def load_apartments():
    """지번 주소 → 아파트명 (아파트가 아닌 지번은 없음). build_apartment_map.py로 생성"""
    if not APT_CSV.exists():
        return {}
    m = pd.read_csv(APT_CSV, dtype=str, encoding="utf-8-sig")
    return dict(zip(m["주소"], m["아파트명"]))


@st.cache_data(ttl=86400, show_spinner=False)
def sgg_codes():
    return {nm: cd for cd, nm in collect.get_districts()}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_live(gu, begin, end):
    """저장 데이터 이후 기간을 사이트에서 가져옴 (같은 조회는 1시간 동안 재요청하지 않음)"""
    code = sgg_codes()[gu]
    rows = []
    cur = begin
    while cur <= end:
        chunk_end = min(cur + timedelta(days=collect.DAYS), end)
        items = collect.get_contracts(code, cur.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d"))
        if any("MESSAGE" in x for x in items):
            raise FetchFailed()   # 예외는 캐시되지 않으므로 다음 조회 때 다시 시도됨
        rows += collect.to_rows(items, gu)
        cur = chunk_end + timedelta(days=1)
    return rows


def one_month_range():
    """오늘 날짜 기준 한 달 전부터 오늘까지"""
    today = pd.Timestamp.today().normalize()
    return (today - pd.DateOffset(months=1)).date(), today.date()


def kpi(icon, label, value, unit="", sub="", sub_class=""):
    return (f'<div class="kpi"><div class="kpi-head"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-icon">{icon}</div></div>'
            f'<div class="kpi-value">{value}<span class="kpi-unit">{unit}</span></div>'
            f'<div class="kpi-sub {sub_class}">{sub}</div></div>')


FAVORITES = ["관악구", "동대문구", "노원구", "강동구"]


def apply_favorite(name):
    """즐겨찾기 버튼: 자치구를 바꾸고 지금 설정된 기간으로 바로 조회 (콜백이라 위젯 값 변경이 가능)"""
    st.session_state.gu_sel = name
    st.session_state.query = (name, "전체", st.session_state.from_date, st.session_state.to_date)


TRADE_CSV = Path(__file__).parent / "apt_trades.csv"


def load_trades():
    """아파트 실거래 (collect_trades.py로 생성). 파일이 바뀔 때만 다시 읽음"""
    if not TRADE_CSV.exists():
        return None
    return _load_trades_file(TRADE_CSV.stat().st_mtime)


@st.cache_resource
def _load_trades_file(_mtime):
    t = pd.read_csv(TRADE_CSV, dtype=str, encoding="utf-8-sig")
    t["계약일"] = pd.to_datetime(t["계약일"], errors="coerce")
    t["거래금액"] = pd.to_numeric(t["거래금액"], errors="coerce")
    t["전용면적"] = pd.to_numeric(t["전용면적"], errors="coerce")
    t["평형"] = (t["전용면적"] / 3.3058).round(0)   # ㎡ → 평 (전용 기준)
    t["층"] = pd.to_numeric(t["층"], errors="coerce")
    return t.dropna(subset=["계약일", "거래금액", "평형"])


def _pyeong_changed(key):
    """평형 버튼 규칙: 전체 선택 → 나머지 해제 / 평형 선택 → 전체 해제 / 아무것도 없으면 전체"""
    cur = list(st.session_state.get(key) or [])
    prev = st.session_state.get(key + "_prev", ["전체"])
    added = [x for x in cur if x not in prev]
    if "전체" in added:
        new = ["전체"]
    elif "전체" in cur and added:
        new = added
    elif not cur:
        new = ["전체"]
    else:
        new = cur
    st.session_state[key] = new
    st.session_state[key + "_prev"] = new


def jibun_of(addr):
    """'관악구 봉천동 1708' → '1708' (주소 끝의 지번)"""
    return str(addr).split()[-1]


@st.dialog("실거래 추이", width="small")
def show_trades(title, addr, gu, dong, jibun):
    """아파트 실거래 팝업 (아실 스타일). 지번 기준 거래, 평형별 색·선택"""
    st.markdown(
        f'<div style="font-size:1.25rem;font-weight:800;color:#0f172a">{title}</div>'
        f'<div style="font-size:.85rem;color:#64748b;margin-bottom:.6rem">{addr}</div>',
        unsafe_allow_html=True)
    # 단지 기본 정보 카드 (연식·세대수는 단지 식별정보, 주차·용적률은 건축물대장 신청 후 표시)
    info = load_apartment_info().get("서울특별시 " + addr)   # (세대 수, 사용승인 연도) 또는 None

    def mini(label, value, sub=""):
        return (f'<div style="border:1px solid #e2e8f0;border-radius:12px;padding:8px 10px;background:#fff">'
                f'<div style="font-size:.72rem;color:#64748b;font-weight:600">{label}</div>'
                f'<div style="font-size:1.02rem;font-weight:800;color:#0f172a;margin-top:2px">{value}</div>'
                f'<div style="font-size:.7rem;color:#94a3b8">{sub}</div></div>')

    households = info[0] if info is not None and pd.notna(info[0]) else ""
    year = info[1] if info is not None and pd.notna(info[1]) else ""
    year_txt = f"{int(float(year))}년" if year else "-"
    age_txt = f"연식 {date.today().year - int(float(year))}년" if year else ""
    hh_txt = f"{int(float(households)):,}세대" if households else "-"
    c_a, c_b = st.columns(2)
    c_a.markdown(mini("사용승인", year_txt, age_txt), unsafe_allow_html=True)
    c_b.markdown(mini("세대 수", hh_txt), unsafe_allow_html=True)
    c_c, c_d = st.columns(2)
    c_c.markdown(mini("주차 대수", "-", "건축물대장 연동 필요"), unsafe_allow_html=True)
    c_d.markdown(mini("용적률", "-", "건축물대장 연동 필요"), unsafe_allow_html=True)
    st.write("")

    trades = load_trades()
    if trades is None:
        st.info("실거래 데이터가 아직 없습니다. collect_trades.py를 실행해 주세요.")
        return
    t = trades[(trades["구"] == gu) & (trades["법정동"] == dong) & (trades["지번"] == jibun)].copy()
    if t.empty:
        st.info("이 지번의 실거래 자료가 없습니다.")
        return
    t["평형"] = t["평형"].astype(int)
    t["억"] = t["거래금액"] / 10000
    # 평형별 대표 전용면적 (사이트 자료는 전용면적 기준이라 아실 평형과 다를 수 있음)
    area_by = t.groupby("평형")["전용면적"].agg(lambda s: int(round(s.mode().iloc[0])))
    t["평형라벨"] = [f"{p}평 (전용 {area_by[p]}㎡)" for p in t["평형"]]
    labels = [f"{p}평 (전용 {area_by[p]}㎡)" for p in sorted(area_by.index)]
    t_all = t.copy()   # 기간 슬라이더는 평형 선택과 무관하게 단지 전체 기간 기준

    # 평형 선택: '전체'가 기본. 전체를 누르면 나머지는 풀리고, 평형을 누르면 전체는 풀림
    pyeong_key = f"pyeong_{gu}_{jibun}"
    chosen = st.pills("평형", ["전체"] + labels, selection_mode="multi", default=["전체"],
                      key=pyeong_key, on_change=_pyeong_changed, args=(pyeong_key,))
    if not chosen:
        chosen = ["전체"]
    if "전체" not in chosen:
        t = t[t["평형라벨"].isin(chosen)]

    # 기간 슬라이더 (기본: 최근 3년)
    dmin, dmax = t_all["계약일"].min().date(), t_all["계약일"].max().date()
    default_start = dmin   # 기본: 2006년부터 전체
    span = st.slider("기간", min_value=dmin, max_value=dmax, value=(default_start, dmax),
                     key=f"range_{gu}_{jibun}")
    t = t[(t["계약일"] >= pd.Timestamp(span[0])) & (t["계약일"] <= pd.Timestamp(span[1]))]
    if t.empty:
        st.info("선택한 기간에 거래가 없습니다.")
        return

    # 최근 거래월 요약 (아실의 '06년 12월 / 매매 50,325 / 2건')
    last_month = t["계약일"].max().to_period("M")
    recent = t[t["계약일"].dt.to_period("M") == last_month]
    st.markdown(
        f'<div style="margin:.4rem 0 .2rem;font-size:.9rem;color:#334155">{last_month.year % 100:02d}년 {last_month.month:02d}월</div>'
        f'<div style="font-size:1.15rem;font-weight:800;color:#2563eb">매매 {recent["거래금액"].mean():,.0f} / {len(recent)}건</div>',
        unsafe_allow_html=True)

    color = alt.Color("평형라벨:N", title=None, sort=labels, scale=alt.Scale(scheme="tableau10"))
    y_axis = alt.Axis(labelExpr="format(datum.value, '.0f') + '억'", titleColor="#475569")

    # 위: 평형별 매매 선 + 점
    line = (alt.Chart(t)
            .mark_line(point=alt.OverlayMarkDef(size=14, filled=True), strokeWidth=1.2, opacity=0.9)
            .encode(
                x=alt.X("계약일:T", title=None, axis=alt.Axis(format="%y년", labelAngle=0)),
                y=alt.Y("억:Q", title=None, scale=alt.Scale(zero=False), axis=y_axis),
                color=color,
                order="계약일:T",
                tooltip=[alt.Tooltip("계약일:T", format="%Y-%m-%d", title="계약일"),
                         alt.Tooltip("단지명:N", title="단지"),
                         alt.Tooltip("평형라벨:N", title="평형"),
                         alt.Tooltip("층:Q", title="층"),
                         alt.Tooltip("거래금액:Q", title="거래금액(만원)", format=",.0f")])
            .properties(height=240, width="container"))

    # 아래: 월별 거래 건수 막대 (평형별 색)
    # 기간이 길면(3년 초과) 막대를 연도별로 묶어서 번지지 않게 함
    yearly = (t["계약일"].max() - t["계약일"].min()).days > 365 * 3
    unit = "Y" if yearly else "M"
    bucket = "연도" if yearly else "월"
    counts = (t.assign(묶음=t["계약일"].dt.to_period(unit).dt.to_timestamp())
               .groupby(["묶음", "평형라벨"], as_index=False).size()
               .rename(columns={"size": "건수"}))
    bars = (alt.Chart(counts)
            .mark_bar(opacity=0.85, cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
            .encode(
                x=alt.X("묶음:T", title=None, axis=alt.Axis(format="%y년", labelAngle=0)),
                y=alt.Y("건수:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d")),
                color=color,
                tooltip=[alt.Tooltip("묶음:T", format="%Y년" if yearly else "%Y-%m", title=bucket),
                         alt.Tooltip("평형라벨:N", title="평형"),
                         alt.Tooltip("건수:Q", title="건수")])
            .properties(height=52, width="container"))

    chart = (alt.vconcat(line, bars)
             .resolve_scale(color="shared", x="shared")
             .configure_view(strokeWidth=0)
             .configure_axis(gridColor="#f1f5f9", labelColor="#475569", domainColor="#cbd5e1")
             .configure_legend(orient="top", labelColor="#334155"))
    st.altair_chart(chart, width="stretch")
    st.caption(f"총 {len(t)}건 · 선·점은 평형별 매매, 아래 막대는 월별 거래 건수")


def trade_trends():
    """(구, 법정동, 지번) → ▲/▼/- : 같은 전용면적의 최근 거래가 직전 거래보다 오르면 ▲, 내리면 ▼"""
    if not TRADE_CSV.exists():
        return {}
    return _trade_trends_file(TRADE_CSV.stat().st_mtime)


@st.cache_resource
def _trade_trends_file(_mtime):
    t = load_trades()
    if t is None:
        return {}
    t = t.assign(면적=t["전용면적"].round(0)).sort_values("계약일")
    out = {}
    for key, g in t.groupby(["구", "법정동", "지번"]):
        last = g.iloc[-1]
        same = g[g["면적"] == last["면적"]]
        if len(same) < 2:
            continue
        prev = same.iloc[-2]
        if last["거래금액"] > prev["거래금액"]:
            out[key] = "▲"
        elif last["거래금액"] < prev["거래금액"]:
            out[key] = "▼"
        else:
            out[key] = "-"
    return out


@st.dialog("알림")
def need_gu_popup():
    st.write("**자치구를 선택해주세요.**")
    st.caption("자치구를 고른 뒤 다시 조회해 주세요.")
    if st.button("확인", type="primary", width="stretch"):
        st.rerun()


df = load()
min_d = df["허가일자"].min().date()
max_d = max(df["허가일자"].max().date(), date.today())
GU_OPTIONS = [PLACEHOLDER_GU] + sorted(df["구"].unique())

st.markdown('<div class="hero"><div class="hero-icon">🏠</div><div>'
            '<div class="hero-title">토지거래허가 현황</div>'
            '<div class="hero-sub">서울 자치구별 토지거래허가 건수를 기간별로 조회합니다 · '
            '원본: 서울 토지거래허가 내역 조회</div></div></div>', unsafe_allow_html=True)

if "query" not in st.session_state:
    st.session_state.query = None  # 조회 버튼을 누르기 전에는 결과를 보여주지 않음
# 기간 기본값은 처음 한 번만 넣음 (값이 바뀌면 위젯이 초기화되므로 key로 관리)
st.session_state.setdefault("from_date", one_month_range()[0])
st.session_state.setdefault("to_date", one_month_range()[1])

# ── 조회 조건 ─────────────────────────────────────
with st.container(border=True):
    st.markdown('<div class="section-title">🔍 조회 조건</div>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 0.8])
    with c1:
        gu_sel = st.selectbox("🏙️ 자치구", GU_OPTIONS, key="gu_sel")
    with c2:
        if gu_sel == PLACEHOLDER_GU:
            st.selectbox("🏘️ 동", ["전체"], disabled=True, key="dong_off")
            dong_sel = "전체"
        else:
            dong_opts = ["전체"] + sorted(df.loc[df["구"] == gu_sel, "동"].unique())
            dong_sel = st.selectbox("🏘️ 동", dong_opts, key=f"dong_{gu_sel}")
    with c3:
        from_sel = st.date_input("📅 시작일", min_value=min_d, max_value=max_d, key="from_date")
    with c4:
        to_sel = st.date_input("📅 종료일", min_value=min_d, max_value=max_d, key="to_date")
    with c5:
        st.write("")
        submitted = st.button("조회하기", type="primary", width="stretch")

    if submitted:
        if gu_sel == PLACEHOLDER_GU:
            need_gu_popup()
        elif from_sel > to_sel:
            st.toast("시작일이 종료일보다 늦습니다.", icon="⚠️")
        else:
            st.session_state.query = (gu_sel, dong_sel, from_sel, to_sel)

    st.caption("⭐ 즐겨찾기 · 누르면 위 기간으로 바로 조회됩니다")
    fav_cols = st.columns(4)
    for col, name in zip(fav_cols, FAVORITES):
        col.button(f"📌 {name}", key=f"fav_{name}", on_click=apply_favorite,
                   args=(name,), width="stretch")

if st.session_state.query is None:
    st.markdown('<div class="empty">🔎<br><br>자치구와 기간을 고른 뒤 <b>조회하기</b>를 누르면 결과가 나옵니다.</div>',
                unsafe_allow_html=True)
    st.stop()

gu, dong, s, e = st.session_state.query
start, end = pd.Timestamp(s), pd.Timestamp(e)
days = (end - start).days + 1

# ── 저장 데이터에 없는 최신 기간은 사이트에서 가져와 합치기 ──────────
today_ts = pd.Timestamp(date.today())
gu_latest = df.loc[df["구"] == gu, "허가일자"].max()
need_from = start if pd.isna(gu_latest) else max(start, gu_latest + pd.Timedelta(days=1))
fetch_end = min(end, today_ts)
if need_from <= fetch_end:
    try:
        with st.spinner("저장되지 않은 최신 데이터를 사이트에서 가져오는 중..."):
            live_rows = fetch_live(gu, need_from.date(), fetch_end.date())
        live = pd.DataFrame(live_rows, columns=collect.COLUMNS).astype(str)
        live["허가일자"] = pd.to_datetime(live["허가일자"])
        keep = ~((df["구"] == gu) & (df["허가일자"] >= need_from) & (df["허가일자"] <= fetch_end))
        df = pd.concat([df[keep], live], ignore_index=True)
        df = df.drop_duplicates(subset=["접수번호", "주소", "허가일자"], keep="last")
    except FetchFailed:
        st.warning("사이트에서 최신 데이터를 가져오지 못했습니다(점검 중일 수 있음). 저장된 데이터만 표시합니다.")

base = df[df["구"] == gu]
if dong != "전체":
    base = base[base["동"] == dong]
cur = base[base["허가일자"].between(start, end)]

st.markdown(f'<div class="period">📅 {start:%Y-%m-%d} ~ {end:%Y-%m-%d} &nbsp;·&nbsp; '
            f'🏙️ {gu} &nbsp;·&nbsp; 🏘️ {dong}</div>', unsafe_allow_html=True)

# ── KPI 카드 ──────────────────────────────────────
total = len(cur)
avg = total / days if days else 0

prev_base = df[df["구"] == gu]
if dong != "전체":
    prev_base = prev_base[prev_base["동"] == dong]
prev = prev_base[prev_base["허가일자"].between(start - pd.Timedelta(days=days),
                                            start - pd.Timedelta(days=1))]
prev_total = len(prev)
diff = total - prev_total
if prev_total:
    change = f"{diff / prev_total * 100:+.1f}%"
    change_sub = f"직전 {days}일 대비 {diff:+,}건"
    change_class = "up" if diff > 0 else "down"   # 늘면 빨강, 줄면 파랑
else:
    change, change_sub, change_class = "-", "직전 기간 데이터 없음", ""

k1, k2, k3 = st.columns(3)
k1.markdown(kpi("📋", "총 허가", f"{total:,}", "건"), unsafe_allow_html=True)
k2.markdown(kpi("📈", "일평균", f"{avg:.1f}", "건/일"), unsafe_allow_html=True)
k3.markdown(kpi("🔄", "직전 기간 대비", change, sub=change_sub, sub_class=change_class),
            unsafe_allow_html=True)

st.write("")

# ── 일별 막대그래프 ───────────────────────────────
# 허가가 있었던 날짜만 가로축에 표시
active_dates = pd.DatetimeIndex(sorted(cur["허가일자"].unique()))
label_order = [d.strftime("%m-%d") for d in active_dates]

with st.container(border=True):
    st.markdown('<div class="section-title">📊 허가 추이 (일별)</div>', unsafe_allow_html=True)
    if cur.empty:
        st.info("선택한 조건에 허가 내역이 없습니다.")
    else:
        axis_x = alt.X("라벨:O", sort=label_order, title=None,
                       axis=alt.Axis(labelAngle=-45, labelOverlap=False))
        axis_y = alt.Y("건수:Q", title="건", axis=alt.Axis(tickMinStep=1, format="d"))

        if dong == "전체":
            # 동을 고르지 않은 경우: 자치구 일별 합계 막대 + 기간 일평균 점선
            daily = (cur.assign(건수=1).groupby("허가일자", as_index=False)["건수"].sum())
            daily["라벨"] = daily["허가일자"].dt.strftime("%m-%d")
            bars = (alt.Chart(daily)
                    .mark_bar(color="#0d9488", cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
                    .encode(x=axis_x, y=axis_y,
                            tooltip=[alt.Tooltip("허가일자:T", format="%Y-%m-%d", title="일자"),
                                     alt.Tooltip("건수:Q", title="건수")]))
            avg_line = (alt.Chart(pd.DataFrame({"건수": [round(avg, 1)]}))
                        .mark_rule(color="#dc2626", strokeDash=[6, 4], strokeWidth=2)
                        .encode(y="건수:Q"))
            chart = bars + avg_line
            st.caption(f"🔴 점선: 기간 일평균 {avg:.1f}건")
        else:
            # 동을 고른 경우: 그 동의 일별 막대
            daily = (cur.assign(건수=1)
                        .groupby(["허가일자", "동"], as_index=False)["건수"].sum())
            grid = pd.MultiIndex.from_product(
                [active_dates, daily["동"].unique()],
                names=["허가일자", "동"])
            daily = (daily.set_index(["허가일자", "동"])
                          .reindex(grid, fill_value=0).reset_index())
            daily["라벨"] = daily["허가일자"].dt.strftime("%m-%d")
            chart = (alt.Chart(daily)
                     .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
                     .encode(x=axis_x, y=axis_y,
                             xOffset=alt.XOffset("동:N"),
                             color=alt.Color("동:N", title=None,
                                             scale=alt.Scale(scheme="tableau20")),
                             tooltip=[alt.Tooltip("허가일자:T", format="%Y-%m-%d", title="일자"),
                                      alt.Tooltip("동:N"),
                                      alt.Tooltip("건수:Q", title="건수")]))

        chart = (chart.properties(width="container", height=320)   # 카드 폭에 맞춰 반응형으로
                      .configure_view(strokeWidth=0)
                      .configure_axis(gridColor="#f1f5f9", labelColor="#475569",
                                      titleColor="#475569", domainColor="#cbd5e1")
                      .configure_legend(orient="top", labelColor="#334155"))
        st.altair_chart(chart, width="stretch")

st.write("")

# ── 일자별 집계 표 ────────────────────────────────
with st.container(border=True):
    st.markdown('<div class="section-title">🗓️ 일자별 집계 (동별)</div>', unsafe_allow_html=True)
    if cur.empty:
        st.info("집계할 내역이 없습니다.")
    else:
        pv = (cur.assign(건수=1)
                 .pivot_table(index="허가일자", columns="동",
                              values="건수", aggfunc="sum", fill_value=0))
        pv = pv.reindex(pd.date_range(start, end), fill_value=0)   # 허가 없는 날도 0으로 표시
        pv = pv[sorted(pv.columns)]
        pv.insert(0, "합계", pv.sum(axis=1))
        pv = pv.sort_index(ascending=False)
        weekday = "월화수목금토일"
        pv.index = [f"{d:%Y-%m-%d} ({weekday[d.weekday()]})" for d in pv.index]
        pv.index.name = "일자"

        st.dataframe(
            pv,
            width="stretch",
            height=min(460, 40 + 35 * len(pv)),
            column_config={
                "합계": st.column_config.ProgressColumn(
                    "합계", format="%d", min_value=0,
                    max_value=int(pv["합계"].max()) or 1),
            },
        )

st.write("")

# ── 상세 내역 / 다운로드 ───────────────────────────
with st.expander("🔍 상세 내역 보기", expanded=True):
    detail = cur.sort_values("허가일자", ascending=False).reset_index(drop=True)
    apt_map = load_apartments()
    apt_names = ("서울특별시 " + detail["주소"].str.strip()).map(apt_map).fillna("")
    detail.insert(detail.columns.get_loc("주소") + 1, "아파트명", apt_names)   # 주소 오른쪽에 표시
    trend = trade_trends()
    detail.insert(detail.columns.get_loc("아파트명") + 1, "추세", [
        trend.get((g, d, str(a).split()[-1]), "") for g, d, a in zip(detail["구"], detail["동"], detail["주소"])])
    view = detail.copy()
    # 지도 칸을 누르면 네이버지도에서 해당 주소 검색 (주소는 URL 인코딩해서 링크에 넣음)
    view.insert(view.columns.get_loc("추세") + 1, "지도", view["주소"].map(
        lambda a: f"https://map.naver.com/p/search/{quote(a)}#지도보기"))
    # 매물 칸을 누르면 네이버부동산 검색 (단지명이 있으면 단지명, 없으면 주소로 검색)
    # 검색어: 아파트면 "구 + 단지명" (네이버 안내 형식 '지역명 + 단지명'), 아니면 "구 + 동 + 지번"
    view.insert(view.columns.get_loc("지도") + 1, "매물", [
        f"https://land.naver.com/search/search.naver?query={quote(f'{gu} {name}' if name else f'{gu} {dg} {jibun_of(addr)}')}#매물보기"
        for gu, dg, name, addr in zip(detail["구"], detail["동"], detail["아파트명"], detail["주소"])])
    st.caption("👆 파란 아파트명을 누르면 그 단지의 실거래 그래프가 뜹니다 · 추세: ▲ 직전 거래보다 상승, ▼ 하락 (같은 지번·전용면적 기준)")
    # 아파트명은 링크처럼 파란 밑줄로 표시 (누르면 실거래 그래프)
    link_style = lambda v: "color:#2563eb;text-decoration:underline;font-weight:600" if v else ""
    trend_style = lambda v: ("color:#dc2626;font-weight:800" if v == "▲"
                             else "color:#2563eb;font-weight:800" if v == "▼" else "")
    styled = view.style.map(link_style, subset=["아파트명"]).map(trend_style, subset=["추세"])
    event = st.dataframe(
        styled, width="stretch", on_select="rerun", selection_mode="single-cell",
        key="detail_table",
        column_config={"지도": st.column_config.LinkColumn("지도", display_text=r"#(.+)"),
                       "매물": st.column_config.LinkColumn("매물", display_text=r"#(.+)"),
                       "추세": st.column_config.TextColumn("추세", width="small")})
    cells = event.selection.cells if event and event.selection else []
    if cells:
        cell = cells[0]
        r = cell["row"] if isinstance(cell, dict) else cell[0]
        col = cell["column"] if isinstance(cell, dict) else cell[1]
        if col == "아파트명":
            row = detail.iloc[r]
            pick_key = f"{r}-{row['주소']}"
            # 같은 칸으로 다른 조건만 바뀌어 다시 실행될 때 팝업이 반복해서 뜨지 않도록 한 번만 연다
            if st.session_state.get("last_pick") != pick_key:
                st.session_state.last_pick = pick_key
                if row["아파트명"]:
                    jibun = str(row["주소"]).split()[-1]
                    show_trades(row["아파트명"], row["주소"], row["구"], row["동"], jibun)
                else:
                    st.toast("아파트가 아닌 지번이라 실거래 그래프가 없습니다.", icon="🏠")
    st.download_button("⬇️ CSV로 내려받기",
                       detail.to_csv(index=False).encode("utf-8-sig"),
                       "허가내역.csv", "text/csv")
