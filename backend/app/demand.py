"""
需要推定エンジン。

商圏(徒歩N分 → 直線距離補正)内の人口・年齢構成・競合医療機関数を集計する。
"""
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

# 徒歩分 → 直線距離半径(m)への変換係数
WALK_SPEED_M_PER_MIN = 80  # 一般的な成人の平均徒歩分速
DETOUR_FACTOR = 1.3  # 道路網の迂回を考慮した経験的補正係数(都市計画分野で一般的な値)


def walk_minutes_to_radius_m(walk_minutes: float) -> float:
    """徒歩N分を、PostGIS検索用の直線距離半径(m)に変換する。

    実際の徒歩距離(道なり) = walk_minutes * WALK_SPEED_M_PER_MIN
    直線距離半径 = 実際の徒歩距離 / DETOUR_FACTOR
    (道路は直線ではなく折れ曲がるため、直線距離は実際の徒歩距離より短くなる)
    """
    walking_distance_m = walk_minutes * WALK_SPEED_M_PER_MIN
    return walking_distance_m / DETOUR_FACTOR


@dataclass
class AgeBracketPopulation:
    age_bracket: str
    male: int = 0
    female: int = 0

    @property
    def total(self) -> int:
        return self.male + self.female


@dataclass
class CatchmentAreaResult:
    latitude: float
    longitude: float
    walk_minutes: float
    radius_m: float
    total_population: int
    total_households: int
    mesh_count: int
    age_breakdown: list[AgeBracketPopulation]
    competitor_count: int
    competitor_department: str | None


def get_catchment_population(
    db: Session,
    latitude: float,
    longitude: float,
    walk_minutes: float,
) -> tuple[int, int, int, list[AgeBracketPopulation]]:
    """商圏内の人口・世帯数・メッシュ数・年齢構成を取得する"""
    radius_m = walk_minutes_to_radius_m(walk_minutes)

    # 商圏内メッシュの人口・世帯数を合算
    summary_sql = text("""
        SELECT
            COUNT(*) AS mesh_count,
            COALESCE(SUM(total_population), 0) AS total_population,
            COALESCE(SUM(household_count), 0) AS total_households
        FROM population_mesh
        WHERE ST_DWithin(
            geom::geography,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
            :radius_m
        )
    """)
    summary_row = db.execute(
        summary_sql, {"lon": longitude, "lat": latitude, "radius_m": radius_m}
    ).fetchone()

    # 商圏内メッシュの年齢階級別人口を合算
    age_sql = text("""
        SELECT
            pma.age_bracket,
            pma.gender,
            SUM(pma.population) AS population
        FROM population_mesh_age pma
        JOIN population_mesh pm ON pma.mesh_code = pm.mesh_code
        WHERE ST_DWithin(
            pm.geom::geography,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
            :radius_m
        )
        GROUP BY pma.age_bracket, pma.gender
    """)
    age_rows = db.execute(
        age_sql, {"lon": longitude, "lat": latitude, "radius_m": radius_m}
    ).fetchall()

    age_map: dict[str, AgeBracketPopulation] = {}
    for bracket, gender, population in age_rows:
        entry = age_map.setdefault(bracket, AgeBracketPopulation(age_bracket=bracket))
        if gender == "male":
            entry.male = population
        elif gender == "female":
            entry.female = population

    age_breakdown = sorted(age_map.values(), key=lambda a: a.age_bracket)

    return (
        summary_row.mesh_count,
        summary_row.total_population,
        summary_row.total_households,
        age_breakdown,
    )


def get_competitor_count(
    db: Session,
    latitude: float,
    longitude: float,
    walk_minutes: float,
    department: str,
) -> int:
    """商圏内の同一診療科の医療機関数をカウントする"""
    radius_m = walk_minutes_to_radius_m(walk_minutes)
    sql = text("""
        SELECT COUNT(*) AS cnt
        FROM medical_institutions
        WHERE department = :department
        AND ST_DWithin(
            geom::geography,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
            :radius_m
        )
    """)
    row = db.execute(
        sql,
        {
            "lon": longitude,
            "lat": latitude,
            "radius_m": radius_m,
            "department": department,
        },
    ).fetchone()
    return row.cnt


def analyze_catchment_area(
    db: Session,
    latitude: float,
    longitude: float,
    walk_minutes: float,
    department: str,
) -> CatchmentAreaResult:
    """商圏分析のメインエントリーポイント"""
    radius_m = walk_minutes_to_radius_m(walk_minutes)
    mesh_count, total_population, total_households, age_breakdown = get_catchment_population(
        db, latitude, longitude, walk_minutes
    )
    competitor_count = get_competitor_count(db, latitude, longitude, walk_minutes, department)

    return CatchmentAreaResult(
        latitude=latitude,
        longitude=longitude,
        walk_minutes=walk_minutes,
        radius_m=radius_m,
        total_population=total_population,
        total_households=total_households,
        mesh_count=mesh_count,
        age_breakdown=age_breakdown,
        competitor_count=competitor_count,
        competitor_department=department,
    )
