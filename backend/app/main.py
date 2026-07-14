from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.demand import analyze_catchment_area, AgeBracketPopulation
from app.bep import calculate_bep, StaffPlan, DEPARTMENT_BENCHMARKS
from app.demand_rate import estimate_theoretical_demand, ANNUAL_WORKING_DAYS

app = FastAPI(title="Clinic Opening Simulator API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/catchment-analysis")
def catchment_analysis(
    latitude: float,
    longitude: float,
    walk_minutes: float = 10.0,
    department: str = "内科",
    db: Session = Depends(get_db),
):
    result = analyze_catchment_area(db, latitude, longitude, walk_minutes, department)
    return {
        "latitude": result.latitude,
        "longitude": result.longitude,
        "walk_minutes": result.walk_minutes,
        "radius_m": round(result.radius_m, 1),
        "total_population": result.total_population,
        "total_households": result.total_households,
        "mesh_count": result.mesh_count,
        "age_breakdown": [
            {"age_bracket": a.age_bracket, "male": a.male, "female": a.female, "total": a.total}
            for a in result.age_breakdown
        ],
        "competitor_count": result.competitor_count,
        "competitor_department": result.competitor_department,
    }


@app.get("/api/bep-diagnosis")
def bep_diagnosis(
    latitude: float,
    longitude: float,
    walk_minutes: float = 10.0,
    department: str = "内科",
    monthly_rent: int = 300_000,
    doctor_count: int = 1,
    nurse_count: int = 1,
    clerk_count: int = 1,
    db: Session = Depends(get_db),
):
    if department not in DEPARTMENT_BENCHMARKS:
        return {"error": f"未対応の診療科です: {department}"}

    catchment = analyze_catchment_area(db, latitude, longitude, walk_minutes, department)

    staff_plan = StaffPlan(
        doctor_count=doctor_count,
        nurse_count=nurse_count,
        clerk_count=clerk_count,
    )

    bep_result = calculate_bep(
        department=department,
        monthly_rent=monthly_rent,
        staff_plan=staff_plan,
    )

    demand_result = estimate_theoretical_demand(db, latitude, longitude, walk_minutes, department)

    return {
        "department": department,
        # 商圏の実データ(人口・競合数)。需要規模の推定値ではなく、判断材料として
        # そのまま提示する
        "catchment": {
            "radius_m": round(catchment.radius_m, 1),
            "total_population": catchment.total_population,
            "competitor_count": catchment.competitor_count,
        },
        "bep": {
            "monthly_rent": bep_result.monthly_rent,
            "monthly_staff_cost": bep_result.monthly_staff_cost,
            "monthly_fixed_cost": bep_result.monthly_fixed_cost,
            "revenue_per_patient": bep_result.revenue_per_patient,
            "breakeven_patients_per_day": bep_result.breakeven_patients_per_day,
            "typical_patients_per_day": bep_result.typical_patients_per_day,
            "is_patient_count_estimated": bep_result.is_patient_count_estimated,
            "is_revenue_estimated": bep_result.is_revenue_estimated,
        },
        # 受療率(患者調査)に基づく商圏全体の理論外来患者数。歯科・美容系は
        # 受療率データが存在しないためhas_rate_data=Falseとなり値は参考にならない
        "theoretical_demand": {
            "has_rate_data": demand_result.has_rate_data,
            "daily_patients_area_total": round(demand_result.daily_patients, 1),
            "annual_patients_area_total": round(demand_result.daily_patients * ANNUAL_WORKING_DAYS),
        },
    }
