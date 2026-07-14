"""
外来受療率(人口10万対)投入バッチ。

厚労省「患者調査」令和5年 全国編 第70表
(性・年齢階級(5歳)×傷病分類×外来(初診-再来)別)から、
内科・小児科・皮膚科・整形外科・耳鼻科の5科について
population_mesh_age.age_bracketと同じ16区分の受療率を算出しoutpatient_ratesに投入する。

歯科・美容系はこの統計の対象外(歯科は別調査、美容系は自由診療のため)のため対象外。

データソース詳細はDATA_SOURCES.md参照。
"""
import os

import requests
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://clinic:clinic@db:5432/clinic_opening_simulator"
)
SOURCE_YEAR = 2023  # 令和5年患者調査
CSV_URL = "https://www.e-stat.go.jp/stat-search/file-download?statInfId=000040234324&fileKind=1"

# population_mesh_age.age_bracketと同じ16区分
AGE_BRACKETS = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
    "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75+",
]

# 傷病大分類の行番号(0-indexed、「外来」ブロック内)
# 内科は複数分類を合算(感染症Ⅰは各科に分散するため意図的に除外)
DISEASE_ROWS = {
    "内科": [18, 21, 25, 29, 34, 40, 52],  # 内分泌代謝/精神行動/神経系/循環器系/呼吸器系/消化器系/腎尿路生殖器系
    "皮膚科": [46],
    "整形外科": [47],
    "耳鼻科": [28],
}
TOTAL_ROW = 6  # 総数行(小児科の年齢別総数受療率に使う)

GENDER_BLOCK_OFFSET = {"male": 24, "female": 48}

# ブロック内インデックス: 0=総数(全年齢),1=0歳,2=1-4,3=5-9,...,16=70-74,17-20=75-79/80-84/85-89/90+,21-23=65+/70+/75+再掲
IDX_0SAI = 1
IDX_1_4 = 2
IDX_5_9_TO_70_74_START = 3  # 5-9歳から70-74歳までは連続14区分
IDX_75PLUS_REAGG = 23  # 75歳以上(再掲)


def fetch_lines() -> list[str]:
    resp = requests.get(CSV_URL, timeout=60)
    resp.raise_for_status()
    text = resp.content.decode("cp932")
    return text.split("\n")


def parse_row_values(lines: list[str], row_idx: int) -> list[str]:
    return lines[row_idx].split(",")


def get_rate(cols: list[str], gender: str, idx: int) -> float:
    offset = GENDER_BLOCK_OFFSET[gender]
    col = 1 + offset + idx
    raw = cols[col].strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0  # 秘匿・非公表等は0扱い(該当データが少ないケース)


def build_age_bracket_rates(lines: list[str], row_idx: int, gender: str) -> dict[str, float]:
    """1つの傷病分類行から、population_mesh_ageと同じ16区分の受療率を作る"""
    cols = parse_row_values(lines, row_idx)

    rate_0_4 = 0.2 * get_rate(cols, gender, IDX_0SAI) + 0.8 * get_rate(cols, gender, IDX_1_4)
    rate_75_plus = get_rate(cols, gender, IDX_75PLUS_REAGG)

    result = {"0-4": rate_0_4, "75+": rate_75_plus}
    # 5-9 ～ 70-74 は連続14区分(AGE_BRACKETSの[1:-1])
    middle_brackets = AGE_BRACKETS[1:-1]
    for offset, bracket in enumerate(middle_brackets):
        result[bracket] = get_rate(cols, gender, IDX_5_9_TO_70_74_START + offset)

    return result


def sum_bracket_dicts(dicts: list[dict[str, float]]) -> dict[str, float]:
    result = {b: 0.0 for b in AGE_BRACKETS}
    for d in dicts:
        for b in AGE_BRACKETS:
            result[b] += d.get(b, 0.0)
    return result


def build_pediatric_rates(lines: list[str], gender: str) -> dict[str, float]:
    """小児科: 総数行から0-14歳部分のみ抽出、それ以外の年齢は0"""
    all_ages = build_age_bracket_rates(lines, TOTAL_ROW, gender)
    result = {b: 0.0 for b in AGE_BRACKETS}
    for b in ["0-4", "5-9", "10-14"]:
        result[b] = all_ages[b]
    return result


def main():
    print("CSVダウンロード中...")
    lines = fetch_lines()
    print(f"総行数: {len(lines)}")

    rows_to_insert = []

    # 傷病分類ベースの受療率は「どの診療科が診たか」を区別しない(呼吸器系疾患には
    # 小児科医が診た子供の風邪も内科医が診た大人の風邪も両方含まれる)。
    # 0-14歳は既に小児科側で年齢ベースの総数受療率としてモデル化済みのため、
    # 内科側で同じ年齢層を計上すると需要を二重計上してしまう。
    # そのため内科は0-14歳(0-4,5-9,10-14)の受療率を0とし、小児科が専任で担う設計とする。
    PEDIATRIC_AGE_BRACKETS = {"0-4", "5-9", "10-14"}

    for department, disease_rows in DISEASE_ROWS.items():
        for gender in ["male", "female"]:
            dicts = [build_age_bracket_rates(lines, row_idx, gender) for row_idx in disease_rows]
            combined = sum_bracket_dicts(dicts)
            for bracket, rate in combined.items():
                if department == "内科" and bracket in PEDIATRIC_AGE_BRACKETS:
                    rate = 0.0
                rows_to_insert.append((department, bracket, gender, rate, SOURCE_YEAR))
        print(f"  {department}: 処理完了")

    for gender in ["male", "female"]:
        pediatric = build_pediatric_rates(lines, gender)
        for bracket, rate in pediatric.items():
            rows_to_insert.append(("小児科", bracket, gender, rate, SOURCE_YEAR))
    print("  小児科: 処理完了")

    print(f"\n投入予定件数: {len(rows_to_insert)}")

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM outpatient_rates")
            execute_values(
                cur,
                "INSERT INTO outpatient_rates (department, age_bracket, gender, rate_per_100k, source_year) VALUES %s",
                rows_to_insert,
            )
        conn.commit()
        print("投入完了")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
