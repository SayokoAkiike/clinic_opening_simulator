"""
東京都限定の人口メッシュ投入バッチ（動作確認用）。
1. 境界データ(Shapefile)をダウンロードして population_mesh に投入
2. 年齢階級別人口(getStatsData)を取得して population_mesh_age に投入
"""
import io
import os
import sys
import zipfile
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
PREF_CODE = "13"
PREF_NAME = "東京都"
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


def find_stats_data_id():
    target_title = f"年齢（５歳階級、４区分）別、男女別人口 {PREF_NAME}"
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


def download_boundary_shapefile():
    resp = requests.get(
        "https://www.e-stat.go.jp/gis/statmap-search/data",
        params={
            "dlserveyId": DL_SURVEY_ID,
            "code": PREF_CODE,
            "coordSys": 1,
            "format": "shape",
            "downloadType": 5,
        },
        timeout=120,
    )
    resp.raise_for_status()
    extract_dir = Path("/tmp/boundary_tokyo")
    extract_dir.mkdir(exist_ok=True)
    zipfile.ZipFile(io.BytesIO(resp.content)).extractall(extract_dir)
    shp_path = next(extract_dir.glob("*.shp"))
    return shp_path


def shape_to_wkt(shp_record):
    geom = shapely_shape(shp_record.__geo_interface__)
    if isinstance(geom, MultiPolygon):
        geom = max(geom.geoms, key=lambda g: g.area)
    return geom.wkt


def main():
    print("=== Step 1: 境界データのダウンロードと population_mesh 投入 ===")
    shp_path = download_boundary_shapefile()
    sf = shapefile.Reader(str(shp_path), encoding="cp932", encodingErrors="replace")

    from collections import defaultdict

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
            print(f"  警告: {key_code} のジオメトリ変換に失敗しました: {e}", file=sys.stderr)
            skipped += 1
            continue
        g = grouped[key_code]
        g["pref_name"] = rec["PREF_NAME"]
        g["geoms"].append(geom)
        g["jinko"] += int(rec["JINKO"]) if rec["JINKO"] is not None else 0
        g["setai"] += int(rec["SETAI"]) if rec["SETAI"] is not None else 0

    mesh_rows = []
    for key_code, g in grouped.items():
        # KEY_CODEが同じ複数パーツがある場合、最大面積のポリゴンを代表ジオメトリとして採用する
        # (population_meshのgeom列はPOLYGON型のため、飛び地のMultiPolygonは統合できない)
        all_polys = []
        for geom in g["geoms"]:
            if isinstance(geom, MultiPolygon):
                all_polys.extend(geom.geoms)
            else:
                all_polys.append(geom)
        largest = max(all_polys, key=lambda p: p.area)
        mesh_rows.append(
            (
                key_code,
                g["pref_name"],
                largest.wkt,
                g["jinko"],
                g["setai"],
                SURVEY_YEAR,
            )
        )
    print(f"  境界データ件数: 元レコード {total_records} 件 → 重複統合後 {len(mesh_rows)} 件 (スキップ {skipped} 件)")

    print("=== Step 2: 年齢階級別人口の取得 ===")
    stats_data_id = find_stats_data_id()
    print(f"  統計表ID: {stats_data_id}")
    class_objs, values = fetch_all_stats_data(stats_data_id)
    print(f"  取得件数(生データ): {len(values)}")
    age_data = parse_age_population(class_objs, values)
    print(f"  年齢データが取れた地域数: {len(age_data)}")

    age_rows = []
    for area_code, brackets in age_data.items():
        for bracket, genders in brackets.items():
            for gender, population in genders.items():
                age_rows.append((area_code, bracket, gender, population))
    print(f"  投入予定の age レコード数: {len(age_rows)}")

    print("=== Step 3: DBへの投入 ===")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
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
            print(f"  population_mesh: {len(mesh_rows)} 件投入")

            cur.execute(
                "DELETE FROM population_mesh_age WHERE mesh_code IN "
                "(SELECT mesh_code FROM population_mesh WHERE prefecture = %s)",
                (PREF_NAME,),
            )
            execute_values(
                cur,
                """
                INSERT INTO population_mesh_age (mesh_code, age_bracket, gender, population)
                VALUES %s
                """,
                age_rows,
            )
            print(f"  population_mesh_age: {len(age_rows)} 件投入")
        conn.commit()
    finally:
        conn.close()

    print("=== 完了 ===")


if __name__ == "__main__":
    main()
