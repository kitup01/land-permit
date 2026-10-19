import altair as alt
import pandas as pd
import streamlit as st
from datetime import date
from pathlib import Path

st.set_page_config(page_title="토지거래허가 현황", page_icon="🏠", layout="wide")

st.markdown("""
<style>
    .block-container {padding-top: 2rem; max-width: 1200px;}
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
    mode = st.radio("기간 방식", ["1개월", "직접 선택"], horizontal=True)
    is_month = mode == "1개월"

    with st.form("query_form"):
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            default_gu = st.session_state.query[0] if st.session_state.query else "전체"
            gu_sel = st.selectbox("🏙️ 자치구", GU_LIST, index=GU_LIST.index(default_gu))
        with c2:
            if is_month:
                m_start, m_end = one_month_range()
                st.date_input("📅 기간 (오늘 기준 1개월)", value=(m_start, m_end), disabled=True)
                date_sel = (m_start, m_end)
            else:
                if st.session_state.query:
                    default_range = (st.session_state.query[1], st.session_state.query[2])
                else:
                    default_range = one_month_range()
                date_sel = st.date_input("📅 기간 (직접 선택)", value=default_range,
                                         min_value=min_d, max_value=max_d)
        with c3:
            st.write("")
            submitted = st.form_submit_button("조회하기", type="primary", use_container_width=True)

        if submitted:
            if isinstance(date_sel, (tuple, list)) and len(date_sel) == 2:
                s, e = date_sel
            else:
                s = e = date_sel[0] if isinstance(date_sel, (tuple, list)) else date_sel
            st.session_state.query = (gu_sel, s, e)

if st.session_state.query is None:
    st.markdown('<div class="empty">🔎<br><br>자치구와 기간을 고른 뒤 <b>조회하기</b>를 누르면 결과가 나옵니다.</div>',
                unsafe_allow_html=True)
    st.stop()

gu, s, e = st.session_state.query
start, end = pd.Timestamp(s), pd.Timestamp(e)
days = (end - start).days + 1

base = df if gu == "전체" else df[df["구"] == gu]
cur = base[base["허가일자"].between(start, end)]

st.markdown(f'<div class="period">📅 {start:%Y-%m-%d} ~ {end:%Y-%m-%d} &nbsp;·&nbsp; '
            f'🏙️ {gu}</div>', unsafe_allow_html=True)

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
k1.markdown(kpi("📋", "총 허가", f"{total:,}", "건"), unsafe_allow_html=True)
k2.markdown(kpi("🏆", top_label, top_name,
                sub=f"{top_cnt:,}건" if top_cnt else "데이터 없음"),
            unsafe_allow_html=True)
k3.markdown(kpi("📈", "일평균", f"{avg:.1f}", "건/일"), unsafe_allow_html=True)
k4.markdown(kpi("🔄", "직전 기간 대비", change, sub=change_sub, sub_class=change_class),
            unsafe_allow_html=True)

st.write("")

# ── 일별 막대그래프 ───────────────────────────────
with st.container(border=True):
    st.markdown('<div class="section-title">📊 허가 추이 (일별)</div>', unsafe_allow_html=True)
    if cur.empty:
        st.info("선택한 조건에 허가 내역이 없습니다.")
    else:
        daily = (cur.assign(건수=1)
                    .groupby(["허가일자", top_col], as_index=False)["건수"].sum())
        # 허가가 없는 날도 0으로 채워서 선이 0에서 끊기지 않게 함
        grid = pd.MultiIndex.from_product(
            [pd.date_range(start, end), daily[top_col].unique()],
            names=["허가일자", top_col])
        daily = (daily.set_index(["허가일자", top_col])
                      .reindex(grid, fill_value=0).reset_index())
        daily["라벨"] = daily["허가일자"].dt.strftime("%m-%d")   # 날짜 칸마다 눈금을 맞추기 위한 글자 라벨
        label_order = [d.strftime("%m-%d") for d in pd.date_range(start, end)]
        chart = (alt.Chart(daily)
                 .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
                 .encode(
                     x=alt.X("라벨:O", sort=label_order, title=None,
                             axis=alt.Axis(labelAngle=-45)),
                     xOffset=alt.XOffset(f"{top_col}:N"),   # 동별 막대를 날짜 안에서 나란히 배치
                     y=alt.Y("건수:Q", title="건",
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

# ── 일자별 집계 표 ────────────────────────────────
with st.container(border=True):
    st.markdown(f'<div class="section-title">🗓️ 일자별 집계 ({top_col}별)</div>',
                unsafe_allow_html=True)
    if cur.empty:
        st.info("집계할 내역이 없습니다.")
    else:
        pv = (cur.assign(건수=1)
                 .pivot_table(index="허가일자", columns=top_col,
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
    st.dataframe(cur.sort_values("허가일자", ascending=False), use_container_width=True)
    st.download_button("⬇️ CSV로 내려받기",
                       cur.to_csv(index=False).encode("utf-8-sig"),
                       "허가내역.csv", "text/csv")
