import argparse
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE = "https://land.seoul.go.kr"
REFERER = BASE + "/land/other/contractStatus.do"
CSV = Path(__file__).parent / "permits.csv"
DAYS = 60            # 사이트는 한 번에 최대 62일까지만 조회 가능
REQ_PAUSE = 2        # 요청 사이 대기(초): 서버에 몰리지 않도록
WINDOW_PAUSE = 10    # 구간(60일) 사이 대기(초)
COLUMNS = ["구", "동", "허가일자", "주소", "지목", "이용목적", "접수번호", "처리"]

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": REFERER})


def get_districts():
    """서울 자치구 목록 (사이트 드롭다운과 동일한 API)"""
    r = session.post(f"{BASE}/land/common/getSggList.do", timeout=30)
    r.raise_for_status()
    return [(d["sggCd"], d["sggNm"]) for d in r.json()["result"]
            if d["sggNm"] != "서울특별시"]


def get_contracts(sgg_cd, begin, end):
    """자치구 하나의 허가 내역 (사이트 검색 버튼과 동일한 API)"""
    r = session.post(f"{BASE}/land/wsklis/getContractList.do",
                     data={"sggCd": sgg_cd, "beginDate": begin, "endDate": end},
                     timeout=30)
    r.raise_for_status()
    return r.json()["result"]


def to_rows(items, gu):
    rows = []
    for it in items:
        if "MESSAGE" in it or not it.get("HNDL_YMD"):
            continue  # 점검 메시지이거나 허가일자가 없는 행은 건너뜀
        ymd = it["HNDL_YMD"]
        address = it["ADDRESS"].strip()
        parts = address.split()
        rows.append({
            "구": gu,
            "동": parts[1] if len(parts) > 1 else "",
            "허가일자": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
            "주소": address,
            "지목": it.get("JIMOK", ""),
            "이용목적": it.get("USE_PURP", ""),
            "접수번호": it.get("ACC_NO", ""),
            "처리": it.get("JOB_GBN_NM", ""),
        })
    return rows


def save(new_rows):
    """새 행을 기존 CSV에 합치고 중복 제거 후 저장"""
    new = pd.DataFrame(new_rows, columns=COLUMNS).astype(str)
    if CSV.exists():
        old = pd.read_csv(CSV, dtype=str)
        df = pd.concat([old, new], ignore_index=True)
    else:
        df = new
    # 같은 접수번호+주소+허가일자는 한 번만 남김 (최신 수집분 우선)
    df = df.drop_duplicates(subset=["접수번호", "주소", "허가일자"], keep="last")
    df = df.sort_values(["허가일자", "구"], ascending=[False, True])
    df.to_csv(CSV, index=False, encoding="utf-8-sig")
    return len(df)


def collect_window(districts, begin, end):
    """begin ~ end 기간(62일 이내)을 자치구별로 가져옴"""
    rows = []
    b, e = begin.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    for sgg_cd, gu in districts:
        items = get_contracts(sgg_cd, b, e)
        rows += to_rows(items, gu)
        print(f"  {gu}: {len(items)}건")
        time.sleep(REQ_PAUSE)
    return rows


def run_daily():
    """매일 실행용: 최근 60일"""
    end = date.today()
    begin = end - timedelta(days=DAYS)
    rows = collect_window(get_districts(), begin, end)
    print(f"총 {save(rows)}건 저장: {CSV}")


def run_backfill(start):
    """과거 데이터를 60일씩 나눠서 천천히 가져옴"""
    districts = get_districts()
    today = date.today()
    cur = start
    total = 0
    while cur <= today:
        end = min(cur + timedelta(days=DAYS), today)
        print(f"[{cur} ~ {end}]")
        rows = collect_window(districts, cur, end)
        total = save(rows)           # 구간마다 저장: 중간에 멈춰도 진행분은 남음
        print(f"  -> 누적 {total}건 저장")
        cur = end + timedelta(days=1)
        if cur <= today:
            time.sleep(WINDOW_PAUSE)
    print(f"완료: 총 {total}건 저장: {CSV}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="과거 데이터부터 가져올 시작일 (예: 2025-01-01)")
    args = parser.parse_args()
    if args.start:
        run_backfill(datetime.strptime(args.start, "%Y-%m-%d").date())
    else:
        run_daily()
