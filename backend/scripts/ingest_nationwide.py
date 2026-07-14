"""
全国47都道府県分の人口メッシュ投入バッチ。
ingest_tokyo.py を汎用化し、都道府県コードをループして実行する。
"""
import io
import os
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import requests
import shapefile
from shapely.geometry import shape as shapely_shape
from shapely.geometry import MultiPolygon
import psycopg2
from psycopg2.extras import execute_values

APP_ID = os.environ["ESTAT_APP_ID"]
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://clinic:clinic@db:5432/clinic_opening_simulator"
)
SURVEY_YEAR = 2020
STATS_CODE = "00200521"
DL_SURVEY_ID = "A002005212020"

GENDER_OFFSETS = {"male": 210, "female": 410}
AGE_OFFSETS = [
    (1, "0-4"), (2, "5-9"), (3, "10-14"), (4, "15-19"), (5, "20-24"),
    (6, "25-29"), (7, "30-34"), (8, "35-39"), (9, "40-44"), (10, "45-49"),
    (11, "50-54"), (12, "55-59"), (13, "60-64"), (14, "65-69"), (15, "70-74"),
    (19, "75+"),
]

PREFECTURES = [
    ("01", "北海道"), ("02", "青森県"), ("03", "岩手県"), ("04", "宮城県"),
    ("05", "秋田県"), ("06", "山形県"), ("07", "福島県"), ("08", "茨城県"),
    ("09", "栃木県"), ("10", "群馬県"), ("11", "埼玉県"), ("12", "千葉県"),
    ("13", "東京都"), ("14", "神奈川県"), ("15", "新潟県"), ("16", "富山県"),
    ("17", "石川県"), ("18", "福井県"), ("19", "山梨県"), ("20", "長野県"),
    ("21", "岐阜県"), ("22", "静岡県"), ("23", "愛知県"), ("24", "三重県"),
    ("25", "滋賀県"), ("26", "京都府"), ("27", "大阪府"), ("28", "兵庫県"),
    ("29", "奈良県"), ("30", "和歌山県"), ("31", "鳥取県"), ("32", "島根県"),
    ("33", "岡山県"), ("34", "広島県"), ("35", "山口県"), ("36", "徳島県"),
    ("37", "香川県"), ("38", "愛媛県"), ("39", "高知県"), ("40", "福岡県"),
    ("41", "佐賀県"), ("42", "長崎県"), ("43", "熊本県"), ("44", "大分県"),
    ("45", "宮崎県"), ("46", "鹿児島県"), ("47", "沖縄県"),
]


def find_stats_data_id(pref_name):
    target_title = f"年齢（５歳階級、４区分）別、男女別人口 {pref_name}"
    start = 1
    while True:
        resp = requests.get(
            "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList",
            params={
                "appId": APP_ID,
                "statsCode": STATS_CODE,
                "searchKind": 2,
                "surveyYears": SURVEY_YEAR,
                "limit": 100,
                "startPosition": start,
            },
            timeout=30,
        ).json()
        datalist = resp.get("GET_STATS_LIST", {}).get("DATALIST_INF", {})
        tables = datalist.get("TABLE_INF", [])
        if isinstance(tables, dict):
            tables = [tables]
        for t in tables:
            title = t.get("TITLE", {})
            title_text = title.get("$") if isinstance(title, dict) else title
            if title_text == target_title:
                return t["@id"]
        result_inf = datalist.get("RESULT_INF", {})
        next_key = result_inf.get("NEXT_KEY")
        if not next_key:
            raise RuntimeError(f"統計表が見つかりませんでした: {target_title}")
        start = int(next_key)


def fetch_all_stats_data(stats_data_id):
    all_values = []
    class_objs = None
    start = 1
    while True:
        resp = requests.get(
            "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData",
            params={
                "appId": APP_ID,
                "statsDataId": stats_data_id,
                "limit": 100000,
                "startPosition": start,
            },
            timeout=60,
        ).json()
        stat_data = resp["GET_STATS_DATA"]["STATISTICAL_DATA"]
        if class_objs is None:
            class_objs = stat_data["CLASS_INF"]["CLASS_OBJ"]
        values = stat_data["DATA_INF"]["VALUE"]
        if isinstance(values, dict):
            values = [values]
        all_values.extend(values)

        result_inf = stat_data.get("RESULT_INF", {})
        next_key = result_inf.get("NEXT_KEY")
        if not next_key:
            break
        start = int(next_key)
    return class_objs, all_values


def get_leaf_area_codes(class_objs):
    area_obj = next(o for o in class_objs if o["@id"] == "area")
    classes = area_obj["CLASS"]
    if isinstance(classes, dict):
        classes = [classes]
    all_codes = {c["@code"] for c in classes}
    parent_codes = {c["@parentCode"] for c in classes if "@parentCode" in c}
    return all_codes - parent_codes


def parse_age_population(class_objs, values):
    leaf_codes = get_leaf_area_codes(class_objs)
    result = {}
    for v in values:
        area_code = v.get("@area")
        if area_code not in leaf_codes:
            continue
        if v.get("@cat02") != "1":
            continue
        cat01 = int(v["@cat01"])
        raw_value = v.get("$")
        if raw_value in (None, "-", ""):
            continue
        try:
            population = int(raw_value)
        except ValueError:
            continue

        for gender, base in GENDER_OFFSETS.items():
            for offset, bracket in AGE_OFFSETS:
                if cat01 == base + offset * 10:
                    result.setdefault(area_code, {}).setdefault(bracket, {})[gender] = population
    return result


def download_boundary_shapefile(pref_code):
    resp = requests.get(
        "https://www.e-stat.go.jp/gis/statmap-search/data",
        params={
            "dlserveyId": DL_SURVEY_ID,
            "code": pref_code,
            "coordSys": 1,
            "format": "shape",
            "downloadType": 5,
        },
        timeout=180,
    )
    resp.raise_for_status()
    extract_dir = Path(f"/tmp/boundary_{pref_code}")
    extract_dir.mkdir(exist_ok=True)
    zipfile.ZipFile(io.BytesIO(resp.content)).extractall(extract_dir)
    shp_path = next(extract_dir.glob("*.shp"))
    return shp_path


def build_mesh_rows(shp_path):
    sf = shapefile.Reader(str(shp_path), encoding="cp932", encodingErrors="replace")
    grouped = defaultdict(lambda: {"pref_name": None, "geoms": [], "jinko": 0, "setai": 0})
    total_records = 0
    skipped = 0
    for sr in sf.iterShapeRecords():
        total_records += 1
        rec = sr.record.as_dict()
        key_code = rec["KEY_CODE"]
        try:
            geom = shapely_shape(sr.shape.__geo_interface__)
        except Exception as e:
            print(f"    警告: {key_code} のジオメトリ変換に失敗: {e}", file=sys.stderr)
            skipped += 1
            continue
        g = grouped[key_code]
        g["pref_name"] = rec["PREF_NAME"]
        g["geoms"].append(geom)
        g["jinko"] += int(rec["JINKO"]) if rec["JINKO"] is not None else 0
        g["setai"] += int(rec["SETAI"]) if rec["SETAI"] is not None else 0

    mesh_rows = []
    for key_code, g in grouped.items():
        all_polys = []
        for geom in g["geoms"]:
            if isinstance(geom, MultiPolygon):
                all_polys.extend(geom.geoms)
            else:
                all_polys.append(geom)
        largest = max(all_polys, key=lambda p: p.area)
        mesh_rows.append(
            (key_code, g["pref_name"], largest.wkt, g["jinko"], g["setai"], SURVEY_YEAR)
        )
    return mesh_rows, total_records, skipped


def upsert_mesh(cur, mesh_rows):
    execute_values(
        cur,
        """
        INSERT INTO population_mesh
            (mesh_code, prefecture, geom, total_population, household_count, source_year)
        VALUES %s
        ON CONFLICT (mesh_code) DO UPDATE SET
            prefecture = EXCLUDED.prefecture,
            geom = EXCLUDED.geom,
            total_population = EXCLUDED.total_population,
            household_count = EXCLUDED.household_count,
            source_year = EXCLUDED.source_year
        """,
        mesh_rows,
        template="(%s, %s, ST_GeomFromText(%s, 4326), %s, %s, %s)",
    )


def upsert_age(cur, pref_name, age_rows):
    cur.execute(
        "DELETE FROM population_mesh_age WHERE mesh_code IN "
        "(SELECT mesh_code FROM population_mesh WHERE prefecture = %s)",
        (pref_name,),
    )
    if age_rows:
        execute_values(
            cur,
            "INSERT INTO population_mesh_age (mesh_code, age_bracket, gender, population) VALUES %s",
            age_rows,
        )


def process_prefecture(conn, pref_code, pref_name):
    shp_path = download_boundary_shapefile(pref_code)
    mesh_rows, total_records, skipped = build_mesh_rows(shp_path)

    stats_data_id = find_stats_data_id(pref_name)
    class_objs, values = fetch_all_stats_data(stats_data_id)
    age_data = parse_age_population(class_objs, values)

    age_rows = []
    for area_code, brackets in age_data.items():
        for bracket, genders in brackets.items():
            for gender, population in genders.items():
                age_rows.append((area_code, bracket, gender, population))

    with conn.cursor() as cur:
        upsert_mesh(cur, mesh_rows)
        upsert_age(cur, pref_name, age_rows)
    conn.commit()

    return {
        "mesh_records": total_records,
        "mesh_merged": len(mesh_rows),
        "mesh_skipped": skipped,
        "age_areas": len(age_data),
        "age_rows": len(age_rows),
    }


def main():
    conn = psycopg2.connect(DATABASE_URL)
    results = {}
    failures = []
    try:
        for i, (pref_code, pref_name) in enumerate(PREFECTURES, start=1):
            print(f"[{i}/{len(PREFECTURES)}] {pref_name} (code={pref_code}) 処理開始...")
            try:
                stats = process_prefecture(conn, pref_code, pref_name)
                results[pref_name] = stats
                print(
                    f"  完了: mesh={stats['mesh_merged']}件"
                    f"(元{stats['mesh_records']}件, skip{stats['mesh_skipped']}件), "
                    f"age_areas={stats['age_areas']}, age_rows={stats['age_rows']}"
                )
            except Exception as e:
                print(f"  失敗: {pref_name}: {e}", file=sys.stderr)
                failures.append((pref_name, str(e)))
                conn.rollback()
            time.sleep(1)  # e-Statへの連続アクセス負荷を抑える
    finally:
        conn.close()

    print("\n=== 全体サマリー ===")
    print(f"成功: {len(results)} / {len(PREFECTURES)} 都道府県")
    total_mesh = sum(r["mesh_merged"] for r in results.values())
    total_age = sum(r["age_rows"] for r in results.values())
    print(f"投入合計: population_mesh {total_mesh}件, population_mesh_age {total_age}件")

    if failures:
        print(f"\n失敗した都道府県 ({len(failures)}件):")
        for pref_name, err in failures:
            print(f"  - {pref_name}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
