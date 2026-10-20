import argparse
import os
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
RETRY_PAUSE = 60     # 점검 응답 시 재시도 전 대기(초)
TRIES = 3
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


def fetch_checked(sgg_cd, begin, end):
    """점검 메시지나 오류면 잠시 뒤 다시 시도. 끝까지 실패하면 None"""
    for attempt in range(1, TRIES + 1):
        try:
            items = get_contracts(sgg_cd, begin, end)
            if not any("MESSAGE" in x for x in items):
                return items
            reason = "점검 응답"
        except requests.RequestException as err:
            reason = f"요청 오류({err.__class__.__name__})"
        if attempt < TRIES:
            print(f"    {reason}: {RETRY_PAUSE}초 뒤 재시도 ({attempt}/{TRIES})")
            time.sleep(RETRY_PAUSE)
    return None


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


def load_stored():
    if CSV.exists():
        return pd.read_csv(CSV, dtype=str, encoding="utf-8-sig")
    return pd.DataFrame(columns=COLUMNS)


def save_all(df):
    df = df.drop_duplicates(subset=["접수번호", "주소", "허가일자"], keep="last")
    df = df.sort_values(["허가일자", "구"], ascending=[False, True])
    # 임시 파일에 먼저 쓰고 교체: 저장 도중 실패해도 원본이 깨지지 않음
    tmp = CSV.with_suffix(".tmp.csv")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    for attempt in range(1, 6):
        try:
            os.replace(tmp, CSV)
            break
        except OSError:
            if attempt == 5:
                raise
            print(f"    파일이 잠겨 있음: 3초 뒤 재시도 ({attempt}/5)")
            time.sleep(3)
    return len(df)


def merge_new(new_rows):
    """새 행을 기존 CSV에 합치고 중복 제거 후 저장 (일별 수집용)"""
    new = pd.DataFrame(new_rows, columns=COLUMNS).astype(str)
    return save_all(pd.concat([load_stored(), new], ignore_index=True))


def replace_window(gu, begin, end, rows):
    """해당 자치구의 begin~end 기간 데이터를 사이트 값으로 통째로 교체 (재동기화용)"""
    df = load_stored()
    in_window = (df["구"] == gu) & (df["허가일자"] >= begin) & (df["허가일자"] <= end)
    new = pd.DataFrame(rows, columns=COLUMNS).astype(str)
    return save_all(pd.concat([df[~in_window], new], ignore_index=True))


def run_daily():
    """매일 실행용: 최근 60일을 다시 받아 누적"""
    end = date.today()
    begin = end - timedelta(days=DAYS)
    b, e = begin.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    rows = []
    for sgg_cd, gu in get_districts():
        items = fetch_checked(sgg_cd, b, e)
        if items is None:
            print(f"  {gu}: 실패 (기존 데이터 유지)")
            continue
        rows += to_rows(items, gu)
        print(f"  {gu}: {len(items)}건")
        time.sleep(REQ_PAUSE)
    print(f"총 {merge_new(rows)}건 저장: {CSV}")


def run_resync(start):
    """start부터 오늘까지 60일 구간별로, 구마다 사이트 값으로 교체하며 검증"""
    districts = get_districts()
    today = date.today()
    failures = []
    cur = start
    while cur <= today:
        end = min(cur + timedelta(days=DAYS), today)
        b, e = cur.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        print(f"[{cur} ~ {end}]")
        for sgg_cd, gu in districts:
            items = fetch_checked(sgg_cd, b, e)
            if items is None:
                failures.append((gu, str(cur), str(end)))
                print(f"  {gu}: 실패 (기존 데이터 유지)")
            else:
                rows = to_rows(items, gu)
                replace_window(gu, str(cur), str(end), rows)
                print(f"  {gu}: 사이트 {len(rows)}건으로 교체")
            time.sleep(REQ_PAUSE)
        cur = end + timedelta(days=1)
        if cur <= today:
            time.sleep(WINDOW_PAUSE)
    print("실패 목록:", failures if failures else "없음")
    print(f"완료: 총 {len(load_stored())}건 저장: {CSV}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resync", metavar="YYYY-MM-DD",
                        help="이 날짜부터 오늘까지 사이트 값으로 재동기화 (검증 겸용)")
    args = parser.parse_args()
    if args.resync:
        run_resync(datetime.strptime(args.resync, "%Y-%m-%d").date())
    else:
        run_daily()
