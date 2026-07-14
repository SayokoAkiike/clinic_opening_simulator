"""
医療機関マスタ投入バッチ。
厚労省「医療情報ネットのオープンデータ」から診療所・歯科診療所を取得し、
診療科目名をMVP向け7分類にマッピングしてmedical_institutionsに投入する。
"""
import csv
import io
import os
import sys
import zipfile
from pathlib import Path

import requests
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://clinic:clinic@db:5432/clinic_opening_simulator"
)

DATA_DATE = "20251201"
BASE_URL = "https://www.mhlw.go.jp/content/11121000"

SOURCES = [
    {
        "source_label": "医療情報ネットオープンデータ(診療所)",
        "facility_zip": f"02-1_clinic_facility_info_{DATA_DATE}.zip",
        "facility_csv": f"02-1_clinic_facility_info_{DATA_DATE}.csv",
        "speciality_zip": f"02-2_clinic_speciality_hours_{DATA_DATE}.zip",
        "speciality_csv": f"02-2_clinic_speciality_hours_{DATA_DATE}.csv",
    },
    {
        "source_label": "医療情報ネットオープンデータ(歯科診療所)",
        "facility_zip": f"03-1_dental_facility_info_{DATA_DATE}.zip",
        "facility_csv": f"03-1_dental_facility_info_{DATA_DATE}.csv",
        "speciality_zip": f"03-2_dental_speciality_hours_{DATA_DATE}.zip",
        "speciality_csv": f"03-2_dental_speciality_hours_{DATA_DATE}.csv",
    },
]

# 優先順位が重要: 先にマッチしたカテゴリが採用される
DEPARTMENT_KEYWORDS = [
    ("美容系", ["美容"]),
    ("小児科", ["小児"]),
    ("皮膚科", ["皮膚"]),
    ("整形外科", ["整形外科"]),
    ("耳鼻科", ["耳鼻"]),
    ("歯科", ["歯科"]),
    ("内科", ["内科"]),
]

PREF_CODE_TO_NAME = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県",
    "06": "山形県", "07": "福島県", "08": "茨城県", "09": "栃木県", "10": "群馬県",
    "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県", "15": "新潟県",
    "16": "富山県", "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県",
    "21": "岐阜県", "22": "静岡県", "23": "愛知県", "24": "三重県", "25": "滋賀県",
    "26": "京都府", "27": "大阪府", "28": "兵庫県", "29": "奈良県", "30": "和歌山県",
    "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県",
    "36": "徳島県", "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県",
    "41": "佐賀県", "42": "長崎県", "43": "熊本県", "44": "大分県", "45": "宮崎県",
    "46": "鹿児島県", "47": "沖縄県",
}


def classify_department(name: str) -> str | None:
    for category, keywords in DEPARTMENT_KEYWORDS:
        if any(kw in name for kw in keywords):
            return category
    return None


def download_and_extract(filename: str, extract_dir: Path) -> Path:
    url = f"{BASE_URL}/{filename}"
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    extract_dir.mkdir(parents=True, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(resp.content)).extractall(extract_dir)
    return extract_dir


def load_facilities(csv_path: Path) -> dict[str, dict]:
    """施設ID -> {name, pref_code, address, lat, lon} の辞書を作る"""
    facilities = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = row.get("所在地座標（緯度）", "").strip()
            lon = row.get("所在地座標（経度）", "").strip()
            if not lat or not lon:
                continue  # 座標なしは投入不可
            facilities[row["ID"]] = {
                "name": row["正式名称"],
                "pref_code": row["都道府県コード"],
                "address": row["所在地"],
                "lat": float(lat),
                "lon": float(lon),
            }
    return facilities


def load_departments(csv_path: Path) -> dict[str, set[str]]:
    """施設ID -> {department1, department2, ...} の辞書を作る(マッピング済み、重複排除)"""
    departments: dict[str, set[str]] = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = classify_department(row["診療科目名"])
            if category is None:
                continue
            departments.setdefault(row["ID"], set()).add(category)
    return departments


def build_rows(facilities: dict, departments: dict, source_label: str) -> list[tuple]:
    rows = []
    for facility_id, facility in facilities.items():
        depts = departments.get(facility_id)
        if not depts:
            continue
        pref_name = PREF_CODE_TO_NAME.get(facility["pref_code"])
        if not pref_name:
            continue
        for dept in depts:
            rows.append(
                (
                    facility["name"],
                    pref_name,
                    facility["address"],
                    dept,
                    None,  # established_date: このデータソースには含まれない
                    source_label,
                    facility["lon"],
                    facility["lat"],
                )
            )
    return rows


def upsert_institutions(conn, rows: list[tuple]):
    with conn.cursor() as cur:
        # 冪等性のため、対象ソースの既存データを削除してから再投入
        sources = {r[5] for r in rows}
        for source_label in sources:
            cur.execute("DELETE FROM medical_institutions WHERE source = %s", (source_label,))

        execute_values(
            cur,
            """
            INSERT INTO medical_institutions
                (name, prefecture, address, department, established_date, source, geom)
            VALUES %s
            """,
            rows,
            template="(%s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
        )
    conn.commit()


def main():
    base_dir = Path("/tmp/medical_ingestion")
    conn = psycopg2.connect(DATABASE_URL)
    total_rows = 0

    try:
        for source in SOURCES:
            print(f"=== {source['source_label']} ===")
            print("  ダウンロード中...")
            facility_dir = download_and_extract(source["facility_zip"], base_dir / "facility")
            speciality_dir = download_and_extract(source["speciality_zip"], base_dir / "speciality")

            print("  施設データ読み込み中...")
            facilities = load_facilities(facility_dir / source["facility_csv"])
            print(f"    座標あり施設数: {len(facilities)}")

            print("  診療科データ読み込み中...")
            departments = load_departments(speciality_dir / source["speciality_csv"])
            print(f"    診療科マッピング済み施設数: {len(departments)}")

            rows = build_rows(facilities, departments, source["source_label"])
            print(f"  投入行数(施設×診療科の組み合わせ): {len(rows)}")

            upsert_institutions(conn, rows)
            total_rows += len(rows)
            print(f"  投入完了\n")

        print(f"=== 全体サマリー: 合計 {total_rows} 件投入 ===")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
