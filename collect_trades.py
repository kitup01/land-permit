"""국토교통부 아파트 매매 실거래가 상세 자료를 서울 자치구·월 단위로 천천히 모아 apt_trades.csv 저장.

실행: python collect_trades.py --gu 동대문구,관악구,강동구,노원구   (기본: 2006-01 ~ 이번 달)
      python collect_trades.py --start 2025-01
      python collect_trades.py --recent 2   (최근 2개월만 갱신)
인증키: .streamlit/secrets.toml 의 MOLIT_KEY (또는 환경변수 MOLIT_KEY)
"""
import argparse
import os
import time
import tomllib
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).parent
OUT = HERE / "apt_trades.csv"
URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
REQ_PAUSE = 2        # 요청 사이 대기(초)
MONTH_PAUSE = 2      # 구·월 사이 추가 대기(초)
TRIES = 3
NUM_ROWS = 1000
COLUMNS = ["구", "법정동", "지번", "단지명", "단지코드", "전용면적", "층", "건축년도",
           "계약일", "거래금액", "거래구분"]

# 서울 자치구 법정동코드(앞 5자리) — 실거래 API의 LAWD_CD와 같은 값
SEOUL_GU = {
    "종로구": "11110", "중구": "11140", "용산구": "11170", "성동구": "11200", "광진구": "11215",
    "동대문구": "11230", "중랑구": "11260", "성북구": "11290", "강북구": "11305", "도봉구": "11320",
    "노원구": "11350", "은평구": "11380", "서대문구": "11410", "마포구": "11440", "양천구": "11470",
    "강서구": "11500", "구로구": "11530", "금천구": "11545", "영등포구": "11560", "동작구": "11590",
    "관악구": "11620", "서초구": "11650", "강남구": "11680", "송파구": "11710", "강동구": "11740",
}


def load_key():
    env = os.environ.get("MOLIT_KEY")
    if env:
        return env
    return tomllib.load(open(HERE / ".streamlit" / "secrets.toml", "rb"))["MOLIT_KEY"]


def months_between(start_ym, end_ym):
    y, m = int(start_ym[:4]), int(start_ym[4:])
    ey, em = int(end_ym[:4]), int(end_ym[4:])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y}{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def fetch_month(session, key, lawd_cd, ym):
    """한 구·한 달의 모든 거래 (페이지 끝까지). 실패하면 None"""
    rows, page = [], 1
    while True:
        params = {"serviceKey": key, "LAWD_CD": lawd_cd, "DEAL_YMD": ym,
                  "pageNo": str(page), "numOfRows": str(NUM_ROWS)}
        ok = False
        for attempt in range(1, TRIES + 1):
            try:
                r = session.get(URL, params=params, timeout=60)
                root = ET.fromstring(r.content)
                code = root.findtext(".//resultCode")
                if r.status_code == 200 and code in (None, "000"):
                    ok = True
                    break
                print(f"      응답 오류 {code or r.status_code}: 재시도 {attempt}/{TRIES}")
            except (requests.RequestException, ET.ParseError) as err:
                print(f"      요청 오류 {err.__class__.__name__}: 재시도 {attempt}/{TRIES}")
            time.sleep(15 * attempt)
        if not ok:
            return None
        items = root.findall(".//item")
        for it in items:
            rows.append({c.tag: (c.text or "").strip() for c in it})
        total = int(root.findtext(".//totalCount") or 0)
        if not items or len(rows) >= total:
            break
        page += 1
        time.sleep(REQ_PAUSE)
    return rows


def to_frame(rows, gu):
    out = []
    for r in rows:
        y, m, d = r.get("dealYear", ""), r.get("dealMonth", "").zfill(2), r.get("dealDay", "").zfill(2)
        out.append({
            "구": gu,
            "법정동": r.get("umdNm", ""),
            "지번": r.get("jibun", ""),
            "단지명": r.get("aptNm", ""),
            "단지코드": r.get("aptSeq", ""),
            "전용면적": r.get("excluUseAr", ""),
            "층": r.get("floor", ""),
            "건축년도": r.get("buildYear", ""),
            "계약일": f"{y}-{m}-{d}",
            "거래금액": r.get("dealAmount", "").replace(",", ""),   # 만원 단위
            "거래구분": r.get("dealingGbn", ""),
        })
    return pd.DataFrame(out, columns=COLUMNS)


def save_gu(gu_frame, gu, months):
    """해당 구의 '받은 달'만 교체 저장 (다른 달·다른 구는 유지)"""
    months_set = {f"{m[:4]}-{m[4:]}" for m in months}
    new = gu_frame.astype(str)
    if OUT.exists():
        old = pd.read_csv(OUT, dtype=str, encoding="utf-8-sig")
        drop = (old["구"] == gu) & (old["계약일"].str[:7].isin(months_set))
        df = pd.concat([old[~drop], new], ignore_index=True)
    else:
        df = new
    df = df.drop_duplicates(subset=["단지코드", "계약일", "층", "전용면적", "거래금액", "지번"], keep="last")
    df.sort_values(["구", "계약일"], ascending=[True, False]).to_csv(OUT, index=False, encoding="utf-8-sig")
    return len(df)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="200601", help="시작 계약년월 (YYYYMM), 기본 2006-01")
    p.add_argument("--gu", help="받을 자치구 (쉼표로 구분, 예: 관악구,노원구). 생략하면 서울 전체")
    p.add_argument("--recent", type=int, help="최근 N개월만 갱신")
    args = p.parse_args()

    today = date.today()
    end_ym = f"{today.year}{today.month:02d}"
    if args.recent:
        # 최근 N개월 (이번 달 포함)
        y, m = today.year, today.month - (args.recent - 1)
        while m <= 0:
            m, y = m + 12, y - 1
        months = months_between(f"{y}{m:02d}", end_ym)
    else:
        months = months_between(args.start, end_ym)

    key = load_key()
    session = requests.Session()
    targets = {g: SEOUL_GU[g] for g in args.gu.split(",")} if args.gu else SEOUL_GU
    print(f"대상: {len(targets)}개 구 × {len(months)}개월 ({months[0]} ~ {months[-1]})")
    for gu, code in targets.items():
        gu_rows = []
        failed = []
        print(f"[{gu}]")
        for ym in months:
            rows = fetch_month(session, key, code, ym)
            if rows is None:
                failed.append(ym)
                print(f"  {ym}: 실패 (건너뜀)")
            else:
                gu_rows += rows
                print(f"  {ym}: {len(rows)}건")
            time.sleep(MONTH_PAUSE)
        total = save_gu(to_frame(gu_rows, gu), gu, months)
        print(f"  -> 저장 누적 {total}건" + (f", 실패 월: {failed}" if failed else ""))
    print(f"완료: {OUT}")


if __name__ == "__main__":
    main()
