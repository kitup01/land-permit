import altair as alt
import pandas as pd
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="토지거래허가 현황", layout="wide")

CSV = Path(__file__).parent / "permits.csv"

if not CSV.exists():
    st.error("permits.csv 파일이 없습니다. 먼저 데이터 파일을 넣어주세요.")
    st.stop()


@st.cache_data(ttl=600)
def load():
    df = pd.read_csv(CSV, dtype=str)
    df["허가일자"] = pd.to_datetime(df["허가일자"])
    return df


df = load()
min_d = df["허가일자"].min().date()
max_d = df["허가일자"].max().date()
GU_LIST = ["전체"] + sorted(df["구"].unique())


def one_month_range():
    """오늘 날짜 기준 한 달 전부터 오늘까지"""
    today = pd.Timestamp.today().normalize()
    return (today - pd.DateOffset(months=1)).date(), today.date()


# ── 조회 조건 (조회 버튼을 눌러야 적용) ─────────────
if "query" not in st.session_state:
    # 처음 열었을 때 기본값: 전체, 1개월
    st.session_state.query = ("전체", *one_month_range())

mode = st.radio("기간 방식", ["1개월", "직접 선택"], horizontal=True)
is_month = mode == "1개월"

with st.form("query_form"):
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        gu_sel = st.selectbox("자치구", GU_LIST,
                              index=GU_LIST.index(st.session_state.query[0]))
    with c2:
        if is_month:
            m_start, m_end = one_month_range()
            st.date_input("기간 (오늘 기준 1개월)", value=(m_start, m_end),
                          disabled=True)
            date_sel = (m_start, m_end)
        else:
            date_sel = st.date_input(
                "기간 (직접 선택)",
                value=(st.session_state.query[1], st.session_state.query[2]),
                min_value=min_d, max_value=max_d)
    with c3:
        st.write("")
        submitted = st.form_submit_button("조회", type="primary",
                                          use_container_width=True)

    if submitted:
        if isinstance(date_sel, (tuple, list)) and len(date_sel) == 2:
            s, e = date_sel
        else:
            # 날짜를 하나만 고른 경우 하루 기간으로 처리
            s = e = date_sel[0] if isinstance(date_sel, (tuple, list)) else date_sel
        st.session_state.query = (gu_sel, s, e)

gu, s, e = st.session_state.query
start, end = pd.Timestamp(s), pd.Timestamp(e)
days = (end - start).days + 1

base = df if gu == "전체" else df[df["구"] == gu]
cur = base[base["허가일자"].between(start, end)]

st.caption(f"기간 {start:%Y-%m-%d} ~ {end:%Y-%m-%d} · 자치구 {gu} · 단위: 건 · "
           "토지거래허가 건수 (자치구청 기준)")

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
change = f"{diff / prev_total * 100:+.1f}%" if prev_total else "-"
change_delta = f"{diff:+,}건" if prev_total else None

k1, k2, k3, k4 = st.columns(4)
k1.metric("총 허가", f"{total:,}건")
k2.metric(top_label, top_name, f"{top_cnt:,}건" if top_cnt else None,
          delta_color="off")
k3.metric("일평균", f"{avg:.1f}건/일")
k4.metric("직전 기간 대비", change, change_delta)

# ── 일별 막대그래프 ───────────────────────────────
st.subheader("허가 추이 (일별)")
if cur.empty:
    st.info("선택한 조건에 허가 내역이 없습니다.")
else:
    daily = (cur.assign(건수=1)
                .groupby(["허가일자", top_col], as_index=False)["건수"].sum())
    chart = (alt.Chart(daily)
             .mark_bar()
             .encode(
                 x=alt.X("허가일자:T", title=None,
                         axis=alt.Axis(format="%m-%d", labelAngle=-45)),
                 y=alt.Y("건수:Q", title="건",
                         scale=alt.Scale(domain=[0, None]),
                         axis=alt.Axis(tickMinStep=1, format="d")),
                 color=alt.Color(f"{top_col}:N", title=None),
                 tooltip=[alt.Tooltip("허가일자:T", format="%Y-%m-%d"),
                          f"{top_col}:N", "건수:Q"])
             .properties(height=380))
    st.altair_chart(chart, use_container_width=True)

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
