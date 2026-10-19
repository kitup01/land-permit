import pandas as pd
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="토지거래허가 현황", layout="wide")
st.title("토지거래허가 현황")

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

gu = st.sidebar.selectbox("자치구", sorted(df["구"].unique()))
start, end = st.sidebar.date_input(
    "기간", [df["허가일자"].min(), df["허가일자"].max()])

sub = df[(df["구"] == gu) &
         df["허가일자"].between(pd.Timestamp(start), pd.Timestamp(end))]

# 일자 x 동 별 건수
pivot = (sub.assign(건수=1)
            .pivot_table(index="허가일자", columns="동",
                         values="건수", aggfunc="sum", fill_value=0)
            .sort_index(ascending=False))
pivot["합계"] = pivot.sum(axis=1)

st.subheader("일자별 건수")
st.dataframe(pivot)

st.subheader("상세 내역")
st.dataframe(sub.sort_values("허가일자", ascending=False))

st.download_button("CSV로 내려받기",
                   sub.to_csv(index=False).encode("utf-8-sig"),
                   "허가내역.csv", "text/csv")
