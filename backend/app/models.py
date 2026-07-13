from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, JSON, Numeric
from sqlalchemy.orm import declarative_base
from geoalchemy2 import Geometry

Base = declarative_base()


class MedicalInstitution(Base):
    __tablename__ = "medical_institutions"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    prefecture = Column(String, nullable=False, index=True)
    address = Column(String, nullable=False)
    department = Column(String, nullable=False, index=True)  # 診療科
    established_date = Column(Date, nullable=True)
    source = Column(String, nullable=False)  # データ出典（都道府県名等）
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PopulationMesh(Base):
    __tablename__ = "population_mesh"

    mesh_code = Column(String, primary_key=True)  # 3次メッシュコード（約1km四方）
    prefecture = Column(String, nullable=False, index=True)
    geom = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    total_population = Column(Integer, nullable=True)
    household_count = Column(Integer, nullable=True)
    source_year = Column(Integer, nullable=False)  # 国勢調査の調査年
    created_at = Column(DateTime, default=datetime.utcnow)


class PopulationMeshAge(Base):
    __tablename__ = "population_mesh_age"

    id = Column(Integer, primary_key=True)
    mesh_code = Column(String, ForeignKey("population_mesh.mesh_code"), nullable=False, index=True)
    age_bracket = Column(String, nullable=False)  # 例: "30-39"
    gender = Column(String, nullable=True)  # 男/女/計
    population = Column(Integer, nullable=False)


class DiagnosisLog(Base):
    __tablename__ = "diagnosis_logs"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    department = Column(String, nullable=False)
    address_input = Column(String, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    conditions = Column(JSON, nullable=True)  # 駅徒歩・駐車場・テナント形態等
    result_summary = Column(JSON, nullable=True)  # 需要推定・BEP診断結果
    email = Column(String, nullable=True, index=True)
    consented_to_contact = Column(Integer, default=0)  # 0/1
