from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.demand import analyze_catchment_area, AgeBracketPopulation

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
