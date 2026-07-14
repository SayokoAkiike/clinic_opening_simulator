"""
受療率ベースの理論需要推定。

商圏内の年齢×性別人口(population_mesh_age)と、傷病分類・年齢ベースの
外来受療率(outpatient_rates)を掛け合わせて、商圏全体の理論外来患者数を算出する。

歯科・美容系はoutpatient_ratesに対象データが無いため、理論需要は算出できない
(Noneを返す)。データ根拠はDATA_SOURCES.md参照。
"""
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.bep import MONTHLY_WORKING_DAYS

# 患者調査の「受療率(人口10万対)」は調査日1日あたりの推計値であり、年間値ではない。
# そのため population * rate / 100000 は既に「1日あたりの理論患者数」を表す。
# (365で割るのは誤り。以前の実装のannual_patientsという命名も誤解を招くため廃止した)
#
# 年間換算には365(暦日)ではなく、bep.pyの損益分岐点計算と同じ稼働日数の前提
# (MONTHLY_WORKING_DAYS×12、週6日診療想定)を使う。損益分岐点は「診療日ベース」の
# 患者数なので、比較対象の理論需要も同じ前提に揃えないと数字の意味が食い違う。
ANNUAL_WORKING_DAYS = MONTHLY_WORKING_DAYS * 12


@dataclass
class TheoreticalDemandResult:
    department: str
    daily_patients: float
    has_rate_data: bool


def estimate_theoretical_demand(
    db: Session,
    latitude: float,
    longitude: float,
    walk_minutes: float,
    department: str,
) -> TheoreticalDemandResult:
    from app.demand import walk_minutes_to_radius_m

    radius_m = walk_minutes_to_radius_m(walk_minutes)

    sql = text("""
        SELECT COALESCE(SUM(pma.population * orr.rate_per_100k / 100000.0), 0) AS daily_patients
        FROM population_mesh_age pma
        JOIN population_mesh pm ON pma.mesh_code = pm.mesh_code
        JOIN outpatient_rates orr
            ON orr.age_bracket = pma.age_bracket
            AND orr.gender = pma.gender
            AND orr.department = :department
        WHERE ST_DWithin(
            pm.geom::geography,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
            :radius_m
        )
    """)
    row = db.execute(
        sql,
        {"lon": longitude, "lat": latitude, "radius_m": radius_m, "department": department},
    ).fetchone()

    daily_patients = float(row.daily_patients)

    # outpatient_ratesにその診療科のデータが1件も無い場合(歯科・美容系)を検知
    has_rate_check = db.execute(
        text("SELECT COUNT(*) AS cnt FROM outpatient_rates WHERE department = :department"),
        {"department": department},
    ).fetchone()
    has_rate_data = has_rate_check.cnt > 0

    return TheoreticalDemandResult(
        department=department,
        daily_patients=daily_patients,
        has_rate_data=has_rate_data,
    )
