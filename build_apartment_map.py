"""한국부동산원 공동주택 단지 식별정보(원본 CSV)에서 아파트만 뽑아 지번 → 단지명 대응표를 만듦.

실행: python build_apartment_map.py
결과: apartment_names.csv (주소, 아파트명) — 앱이 상세 내역에 아파트명을 붙일 때 사용
"""
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RAW = HERE / "한국부동산원_공동주택 단지 식별정보_기본정보_20260831.csv"
OUT = HERE / "apartment_names.csv"
APARTMENT_CODE = "1"   # 단지종류 1 = 아파트 (2 = 연립·빌라, 3 = 기타로 확인)


def pick_name(row):
    """건축물대장 단지명을 우선, 없으면 도로명 단지명, 그다음 공시가격 단지명"""
    for col in ["단지명_건축물대장", "단지명_도로명주소", "단지명_공시가격"]:
        value = row.get(col)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def main():
    raw = pd.read_csv(RAW, dtype=str, encoding="cp949")
    apt = raw[raw["단지종류"] == APARTMENT_CODE].copy()
    apt["아파트명"] = apt.apply(pick_name, axis=1)
    apt = apt[apt["아파트명"] != ""]
    # 같은 지번에 단지가 여러 개면 이름을 / 로 이어 붙임
    out = (apt.groupby(apt["주소"].str.strip(), as_index=False)["아파트명"]
              .agg(lambda names: " / ".join(dict.fromkeys(names))))
    out.columns = ["주소", "아파트명"]
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"아파트 지번 {len(out)}건 저장: {OUT}")


if __name__ == "__main__":
    main()
