import altair as alt
import pandas as pd
import streamlit as st
from datetime import date
from pathlib import Path

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
        div[data-testid="stVegaLiteChart"], div[data-testid="stArrowVegaLiteChart"] {
            overflow-x: auto; width: 100%; -webkit-overflow-scrolling: touch;
        }
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
    c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
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
    with c3:
        if st.session_state.query:
            default_range = (st.session_state.query[2], st.session_state.query[3])
        else:
            default_range = one_month_range()   # 처음 열면 한 달 전 ~ 오늘
        date_sel = st.date_input("📅 기간", value=default_range,
                                 min_value=min_d, max_value=max_d)
    with c4:
        st.write("")
        submitted = st.button("조회하기", type="primary", use_container_width=True)

    if submitted:
        if gu_sel == "전체":
            need_gu_popup()
        else:
            if isinstance(date_sel, (tuple, list)) and len(date_sel) == 2:
                s, e = date_sel
            else:
                s = e = date_sel[0] if isinstance(date_sel, (tuple, list)) else date_sel
            st.session_state.query = (gu_sel, dong_sel, s, e)

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

# ── KPI 카드 (휴대폰에서도 2x2) ───────────────────
total = len(cur)
avg = total / days if days else 0

top = cur["동"].value_counts()
top_name = top.index[0] if len(top) else "-"
top_cnt = int(top.iloc[0]) if len(top) else 0

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

k1, k2 = st.columns(2)
k3, k4 = st.columns(2)
k1.markdown(kpi("📋", "총 허가", f"{total:,}", "건"), unsafe_allow_html=True)
k2.markdown(kpi("🏆", "최다 동", top_name,
                sub=f"{top_cnt:,}건" if top_cnt else "데이터 없음"),
            unsafe_allow_html=True)
k3.markdown(kpi("📈", "일평균", f"{avg:.1f}", "건/일"), unsafe_allow_html=True)
k4.markdown(kpi("🔄", "직전 기간 대비", change, sub=change_sub, sub_class=change_class),
            unsafe_allow_html=True)

st.write("")

# ── 일별 막대그래프 ───────────────────────────────
label_order = [d.strftime("%m-%d") for d in pd.date_range(start, end)]
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
            daily = (cur.assign(건수=1).groupby("허가일자", as_index=False)["건수"].sum()
                        .set_index("허가일자")
                        .reindex(pd.date_range(start, end), fill_value=0)
                        .rename_axis("허가일자").reset_index())
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
                [pd.date_range(start, end), daily["동"].unique()],
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

        chart = (chart.properties(width=max(360, days * 26), height=320)
                      .configure_view(strokeWidth=0)
                      .configure_axis(gridColor="#f1f5f9", labelColor="#475569",
                                      titleColor="#475569", domainColor="#cbd5e1")
                      .configure_legend(orient="top", labelColor="#334155"))
        st.altair_chart(chart, use_container_width=False)   # 고정 폭: 휴대폰에서는 옆으로 밀어서 봄

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
    st.dataframe(cur.sort_values("허가일자", ascending=False), use_container_width=True)
    st.download_button("⬇️ CSV로 내려받기",
                       cur.to_csv(index=False).encode("utf-8-sig"),
                       "허가내역.csv", "text/csv")
