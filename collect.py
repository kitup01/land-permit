import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE = "https://land.seoul.go.kr"
REFERER = BASE + "/land/other/contractStatus.do"
CSV = Path(__file__).parent / "permits.csv"
DAYS = 60  # 사이트는 한 번에 최대 62일까지만 조회 가능
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


def main():
    end = date.today()
    begin = end - timedelta(days=DAYS)
    b, e = begin.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    new_rows = []
    for sgg_cd, gu in get_districts():
        items = get_contracts(sgg_cd, b, e)
        new_rows += to_rows(items, gu)
        print(f"{gu}: {len(items)}건")
        time.sleep(1)  # 서버에 부담 주지 않도록 잠시 쉼

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
    print(f"총 {len(df)}건 저장: {CSV}")


if __name__ == "__main__":
    main()
