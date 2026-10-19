import altair as alt
import html
import threading
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from datetime import date
from pathlib import Path
from urllib.parse import quote

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

if not CSV.exists():
    st.error("permits.csv 파일이 없습니다. 먼저 데이터 파일을 넣어주세요.")
    st.stop()


@st.cache_data(ttl=600)
def load():
    df = pd.read_csv(CSV, dtype=str)
    df["허가일자"] = pd.to_datetime(df["허가일자"])
    return df


def one_month_range():
    """오늘 날짜 기준 한 달 전부터 오늘까지"""
    today = pd.Timestamp.today().normalize()
    return (today - pd.DateOffset(months=1)).date(), today.date()


def kpi(icon, label, value, unit="", sub="", sub_class=""):
    return (f'<div class="kpi"><div class="kpi-head"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-icon">{icon}</div></div>'
            f'<div class="kpi-value">{value}<span class="kpi-unit">{unit}</span></div>'
            f'<div class="kpi-sub {sub_class}">{sub}</div></div>')


def kakao_keys():
    """Streamlit Secrets에서 카카오 키를 읽음 (설정이 없으면 None)"""
    try:
        return st.secrets.get("KAKAO_JS_KEY"), st.secrets.get("KAKAO_REST_KEY")
    except Exception:
        return None, None


DAILY_KAKAO_LIMIT = 10_000   # 하루 좌표 조회 최대 건수


class KakaoLimitReached(Exception):
    pass


@st.cache_resource
def kakao_counter():
    return {"date": None, "count": 0, "lock": threading.Lock()}


def take_kakao_call():
    """오늘 좌표 조회 횟수를 1 올리고, 한도 안이면 True 반환"""
    c = kakao_counter()
    today = date.today()
    with c["lock"]:
        if c["date"] != today:          # 날짜가 바뀌면 0부터 다시 셈
            c["date"], c["count"] = today, 0
        if c["count"] >= DAILY_KAKAO_LIMIT:
            return False
        c["count"] += 1
        return True


@st.cache_data(ttl=86400, show_spinner=False)
def geocode(address, rest_key):
    """지번 주소 → (위도, 경도). 카카오 로컬 API 사용 (같은 주소는 하루 한 번만 호출)"""
    if not take_kakao_call():
        raise KakaoLimitReached()
    r = requests.get("https://dapi.kakao.com/v2/local/search/address.json",
                     params={"query": f"서울특별시 {address}"},
                     headers={"Authorization": f"KakaoAK {rest_key}"}, timeout=10)
    r.raise_for_status()
    docs = r.json().get("documents", [])
    if not docs:
        return None
    return float(docs[0]["y"]), float(docs[0]["x"])


def kakao_map_html(js_key, lat, lng, text):
    """말풍선(커스텀 오버레이)이 붙은 작은 카카오 지도"""
    bubble = html.escape(text)
    return f"""
<div id="map" style="width:100%;height:240px;border-radius:12px;overflow:hidden;"></div>
<script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={js_key}&autoload=false"></script>
<script>
kakao.maps.load(function () {{
  var pos = new kakao.maps.LatLng({lat}, {lng});
  var map = new kakao.maps.Map(document.getElementById('map'), {{ center: pos, level: 4 }});
  new kakao.maps.Marker({{ position: pos }}).setMap(map);
  var content = '<div style="padding:6px 10px;background:#fff;border:1px solid #cbd5e1;border-radius:10px;font-size:12px;color:#0f172a;box-shadow:0 2px 6px rgba(0,0,0,.15);white-space:nowrap;">{bubble}</div>';
  new kakao.maps.CustomOverlay({{ position: pos, content: content, yAnchor: 2.4 }}).setMap(map);
}});
</script>
"""


@st.dialog("알림")
def need_gu_popup():
    st.write("**자치구를 선택해주세요.**")
    st.caption("'전체'는 조회할 수 없습니다. 자치구를 고른 뒤 다시 조회해 주세요.")
    if st.button("확인", type="primary", use_container_width=True):
        st.rerun()


df = load()
min_d = df["허가일자"].min().date()
max_d = max(df["허가일자"].max().date(), date.today())
GU_LIST = ["전체"] + sorted(df["구"].unique())

st.markdown('<div class="hero"><div class="hero-icon">🏠</div><div>'
            '<div class="hero-title">토지거래허가 현황</div>'
            '<div class="hero-sub">서울 자치구별 토지거래허가 건수를 기간별로 조회합니다 · '
            '원본: 서울 토지거래허가 내역 조회</div></div></div>', unsafe_allow_html=True)

if "query" not in st.session_state:
    st.session_state.query = None  # 조회 버튼을 누르기 전에는 결과를 보여주지 않음

# ── 조회 조건 ─────────────────────────────────────
with st.container(border=True):
    st.markdown('<div class="section-title">🔍 조회 조건</div>', unsafe_allow_html=True)

    prev_gu = st.session_state.query[0] if st.session_state.query else "전체"
    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 0.8])
    with c1:
        gu_sel = st.selectbox("🏙️ 자치구", GU_LIST, index=GU_LIST.index(prev_gu))
    with c2:
        if gu_sel == "전체":
            dong_sel = st.selectbox("🏘️ 동", ["전체"], disabled=True)
        else:
            dong_opts = ["전체"] + sorted(df.loc[df["구"] == gu_sel, "동"].unique())
            prev_dong = (st.session_state.query[1]
                         if st.session_state.query and prev_gu == gu_sel else "전체")
            dong_sel = st.selectbox("🏘️ 동", dong_opts,
                                    index=dong_opts.index(prev_dong)
                                    if prev_dong in dong_opts else 0)

    if st.session_state.query:
        dflt_s, dflt_e = st.session_state.query[2], st.session_state.query[3]
    else:
        dflt_s, dflt_e = one_month_range()   # 처음 열면 한 달 전 ~ 오늘
    with c3:
        from_sel = st.date_input("📅 시작일", value=dflt_s, min_value=min_d, max_value=max_d)
    with c4:
        to_sel = st.date_input("📅 종료일", value=dflt_e, min_value=min_d, max_value=max_d)
    with c5:
        st.write("")
        submitted = st.button("조회하기", type="primary", use_container_width=True)

    if submitted:
        if gu_sel == "전체":
            need_gu_popup()
        elif from_sel > to_sel:
            st.toast("시작일이 종료일보다 늦습니다.", icon="⚠️")
        else:
            st.session_state.query = (gu_sel, dong_sel, from_sel, to_sel)

if st.session_state.query is None:
    st.markdown('<div class="empty">🔎<br><br>자치구와 기간을 고른 뒤 <b>조회하기</b>를 누르면 결과가 나옵니다.</div>',
                unsafe_allow_html=True)
    st.stop()

gu, dong, s, e = st.session_state.query
start, end = pd.Timestamp(s), pd.Timestamp(e)
days = (end - start).days + 1

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
        st.altair_chart(chart, use_container_width=True)

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
            use_container_width=True,
            height=min(460, 40 + 35 * len(pv)),
            column_config={
                "합계": st.column_config.ProgressColumn(
                    "합계", format="%d", min_value=0,
                    max_value=int(pv["합계"].max()) or 1),
            },
        )

st.write("")

# ── 상세 내역 / 다운로드 ───────────────────────────
with st.expander("🔍 상세 내역 보기"):
    detail = cur.sort_values("허가일자", ascending=False).reset_index(drop=True)
    view = detail.copy()   # 주소 칸 자체를 카카오맵 링크로 (글자는 주소 그대로 표시)
    view["주소"] = view["주소"].map(lambda a: f"https://map.kakao.com/?q={a}")
    event = st.dataframe(
        view, use_container_width=True, on_select="rerun",
        selection_mode="single-row", key="detail_table",
        column_config={"주소": st.column_config.LinkColumn("주소", display_text=r"q=(.+)")})
    picked_rows = event.selection.rows if event and event.selection else []
    if picked_rows:
        row = detail.iloc[picked_rows[0]]
        pick = row["주소"]
        text = f"{pick} · {row['허가일자']:%Y-%m-%d} · {row['이용목적']}"
        st.markdown('<div class="section-title">📍 선택한 위치</div>', unsafe_allow_html=True)
        st.link_button("🗺️ 카카오맵에서 보기", f"https://map.kakao.com/?q={quote(pick)}")
        js_key, rest_key = kakao_keys()
        if js_key and rest_key:
            try:
                coords = geocode(pick, rest_key)
            except KakaoLimitReached:
                st.caption("오늘 카카오 좌표 조회 한도(1만 건)에 도달해 지도를 표시하지 못했습니다. 내일 다시 시도해 주세요.")
            else:
                if coords:
                    components.html(kakao_map_html(js_key, coords[0], coords[1], text), height=260)
                else:
                    st.caption("주소로 위치를 찾지 못했습니다.")
        else:
            st.caption("카카오 키(Secrets)를 설정하면 여기에 지도와 말풍선이 표시됩니다.")
    if not picked_rows:
        st.caption("행을 누르면 그 주소의 위치를 카카오맵에서 볼 수 있습니다.")
    st.download_button("⬇️ CSV로 내려받기",
                       cur.to_csv(index=False).encode("utf-8-sig"),
                       "허가내역.csv", "text/csv")
