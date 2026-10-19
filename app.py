import altair as alt
import pandas as pd
import streamlit as st
from datetime import date
from pathlib import Path

st.set_page_config(page_title="토지거래허가 현황", page_icon="🏠", layout="wide")

st.markdown("""
<style>
    .block-container {padding-top: 2.2rem; max-width: 1180px;}
    .hero-title {font-size: 1.9rem; font-weight: 800; color: #0f172a; margin-bottom: .2rem;}
    .hero-sub {color: #64748b; font-size: .95rem; margin-bottom: 1.4rem;}
    .kpi {background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px;
          padding: 18px 20px; height: 100%; box-shadow: 0 1px 2px rgba(15,23,42,.04);}
    .kpi-label {color: #64748b; font-size: .85rem; font-weight: 600;}
    .kpi-value {color: #0f172a; font-size: 1.7rem; font-weight: 800; margin-top: 6px;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
    .kpi-unit {font-size: .95rem; font-weight: 600; color: #475569; margin-left: 4px;}
    .kpi-sub {color: #64748b; font-size: .85rem; margin-top: 4px;}
    .up {color: #dc2626; font-weight: 600;}
    .down {color: #2563eb; font-weight: 600;}
    .period {color: #475569; font-size: .9rem; margin: 1.2rem 0 .6rem;}
    .empty {text-align: center; padding: 70px 20px; color: #64748b; font-size: 1rem;
            background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 16px;}
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


def kpi(label, value, unit="", sub="", sub_class=""):
    return (f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}<span class="kpi-unit">{unit}</span></div>'
            f'<div class="kpi-sub {sub_class}">{sub}</div></div>')


df = load()
min_d = df["허가일자"].min().date()
max_d = max(df["허가일자"].max().date(), date.today())
GU_LIST = ["전체"] + sorted(df["구"].unique())

st.markdown('<div class="hero-title">🏠 토지거래허가 현황</div>'
            '<div class="hero-sub">서울 자치구별 토지거래허가 건수를 기간별로 조회합니다. '
            '원본: 서울 토지거래허가 내역 조회</div>', unsafe_allow_html=True)

if "query" not in st.session_state:
    st.session_state.query = None  # 조회 버튼을 누르기 전에는 결과를 보여주지 않음

# ── 조회 조건 ─────────────────────────────────────
with st.container(border=True):
    mode = st.radio("기간 방식", ["1개월", "직접 선택"], horizontal=True)
    is_month = mode == "1개월"

    with st.form("query_form"):
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            default_gu = st.session_state.query[0] if st.session_state.query else "전체"
            gu_sel = st.selectbox("자치구", GU_LIST, index=GU_LIST.index(default_gu))
        with c2:
            if is_month:
                m_start, m_end = one_month_range()
                st.date_input("기간 (오늘 기준 1개월)", value=(m_start, m_end), disabled=True)
                date_sel = (m_start, m_end)
            else:
                if st.session_state.query:
                    default_range = (st.session_state.query[1], st.session_state.query[2])
                else:
                    default_range = one_month_range()
                date_sel = st.date_input("기간 (직접 선택)", value=default_range,
                                         min_value=min_d, max_value=max_d)
        with c3:
            st.write("")
            submitted = st.form_submit_button("조회", type="primary", use_container_width=True)

        if submitted:
            if isinstance(date_sel, (tuple, list)) and len(date_sel) == 2:
                s, e = date_sel
            else:
                s = e = date_sel[0] if isinstance(date_sel, (tuple, list)) else date_sel
            st.session_state.query = (gu_sel, s, e)

if st.session_state.query is None:
    st.markdown('<div class="empty">자치구와 기간을 고른 뒤 <b>조회</b>를 누르면 결과가 나옵니다.</div>',
                unsafe_allow_html=True)
    st.stop()

gu, s, e = st.session_state.query
start, end = pd.Timestamp(s), pd.Timestamp(e)
days = (end - start).days + 1

base = df if gu == "전체" else df[df["구"] == gu]
cur = base[base["허가일자"].between(start, end)]

st.markdown(f'<div class="period">📅 {start:%Y-%m-%d} ~ {end:%Y-%m-%d} &nbsp;·&nbsp; '
            f'자치구: <b>{gu}</b></div>', unsafe_allow_html=True)

# ── KPI 카드 ──────────────────────────────────────
total = len(cur)
avg = total / days if days else 0

if gu == "전체":
    top_label, top_col = "최다 자치구", "구"
else:
    top_label, top_col = "최다 동", "동"
top = cur[top_col].value_counts()
top_name = top.index[0] if len(top) else "-"
top_cnt = int(top.iloc[0]) if len(top) else 0

prev = base[base["허가일자"].between(start - pd.Timedelta(days=days),
                                  start - pd.Timedelta(days=1))]
prev_total = len(prev)
diff = total - prev_total
if prev_total:
    change = f"{diff / prev_total * 100:+.1f}%"
    change_sub = f"직전 {days}일 대비 {diff:+,}건"
    change_class = "up" if diff > 0 else "down"   # 늘면 빨강, 줄면 파랑
else:
    change, change_sub, change_class = "-", "직전 기간 데이터 없음", ""

k1, k2, k3, k4 = st.columns(4)
k1.markdown(kpi("총 허가", f"{total:,}", "건"), unsafe_allow_html=True)
k2.markdown(kpi(top_label, top_name,
                sub=f"{top_cnt:,}건" if top_cnt else "데이터 없음"),
            unsafe_allow_html=True)
k3.markdown(kpi("일평균", f"{avg:.1f}", "건/일"), unsafe_allow_html=True)
k4.markdown(kpi("직전 기간 대비", change, sub=change_sub, sub_class=change_class),
            unsafe_allow_html=True)

st.write("")

# ── 일별 막대그래프 ───────────────────────────────
with st.container(border=True):
    st.markdown("**허가 추이 (일별)**")
    if cur.empty:
        st.info("선택한 조건에 허가 내역이 없습니다.")
    else:
        daily = (cur.assign(건수=1)
                    .groupby(["허가일자", top_col], as_index=False)["건수"].sum())
        chart = (alt.Chart(daily)
                 .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                 .encode(
                     x=alt.X("허가일자:T", title=None,
                             axis=alt.Axis(format="%m-%d", labelAngle=-45)),
                     y=alt.Y("건수:Q", title="건",
                             scale=alt.Scale(domain=[0, None]),
                             axis=alt.Axis(tickMinStep=1, format="d")),
                     color=alt.Color(f"{top_col}:N", title=None,
                                     scale=alt.Scale(scheme="tableau20")),
                     tooltip=[alt.Tooltip("허가일자:T", format="%Y-%m-%d", title="일자"),
                              alt.Tooltip(f"{top_col}:N", title=top_col),
                              alt.Tooltip("건수:Q", title="건수")])
                 .properties(height=380)
                 .configure_view(strokeWidth=0)
                 .configure_axis(gridColor="#f1f5f9", labelColor="#475569",
                                 titleColor="#475569", domainColor="#cbd5e1")
                 .configure_legend(orient="top", labelColor="#334155"))
        st.altair_chart(chart, use_container_width=True)

st.write("")

# ── 상세 표 / 다운로드 ─────────────────────────────
with st.expander("일자 × 동 표"):
    pivot = (cur.assign(건수=1)
                .pivot_table(index="허가일자", columns="동",
                             values="건수", aggfunc="sum", fill_value=0)
                .sort_index(ascending=False))
    pivot["합계"] = pivot.sum(axis=1)
    st.dataframe(pivot)

with st.expander("상세 내역"):
    st.dataframe(cur.sort_values("허가일자", ascending=False))
    st.download_button("CSV로 내려받기",
                       cur.to_csv(index=False).encode("utf-8-sig"),
                       "허가내역.csv", "text/csv")
