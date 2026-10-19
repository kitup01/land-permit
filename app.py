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
latest = df["허가일자"].max()          # 데이터의 가장 최근 허가일을 기준일로 사용
PERIODS = {"1주": 7, "1개월": 30, "전체": None}

# ── 필터 ──────────────────────────────────────────
c1, c2 = st.columns([1, 2])
with c1:
    gu = st.selectbox("자치구", ["전체"] + sorted(df["구"].unique()))
with c2:
    period = st.radio("기간", list(PERIODS), index=1, horizontal=True)

base = df if gu == "전체" else df[df["구"] == gu]
days = PERIODS[period]
if days is None:
    start = df["허가일자"].min()
else:
    start = latest - pd.Timedelta(days=days - 1)
cur = base[base["허가일자"].between(start, latest)]

st.caption(f"기간 {start:%Y-%m-%d} ~ {latest:%Y-%m-%d} · 단위: 건 · "
           "토지거래허가 건수(자치구청) · 원본: 서울 토지거래허가 내역 조회")

# ── KPI 카드 ──────────────────────────────────────
total = len(cur)
span = (latest - start).days + 1
avg = total / span if span else 0

if gu == "전체":
    top_label, top_col = "최다 자치구", "구"
else:
    top_label, top_col = "최다 동", "동"
top = cur[top_col].value_counts()
top_name = top.index[0] if len(top) else "-"
top_cnt = int(top.iloc[0]) if len(top) else 0

if days is not None:
    prev = base[base["허가일자"].between(start - pd.Timedelta(days=days),
                                      start - pd.Timedelta(days=1))]
    prev_total = len(prev)
    diff = total - prev_total
    change = f"{diff / prev_total * 100:+.1f}%" if prev_total else "-"
    change_delta = f"{diff:+,}건"
else:
    change, change_delta = "-", None

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
