"""
損益分岐点(BEP)診断エンジン。

想定家賃・スタッフ構成から固定費を算出し、診療科別の患者数目安・単価から
損益分岐点患者数を算出、商圏の理論患者数(需要)と比較する。

データ根拠は DATA_SOURCES.md を参照。
"""
from dataclasses import dataclass

# ============================================================
# 人件費(実測): 第25回医療経済実態調査(令和6年度、一般診療所・医療法人)
# 年間給与+賞与の平均額。DATA_SOURCES.md参照。
# ============================================================
ANNUAL_SALARY = {
    "doctor": 10_989_889,       # 医師
    "nurse": 4_131_716,         # 看護職員
    "nurse_aide": 2_916_984,    # 看護補助職員
    "medical_technician": 4_273_294,  # 医療技術員
    "clerk": 3_388_640,         # 事務職員
    "other": 2_830_601,         # その他職員
}

# ============================================================
# 診療科別の1日あたり患者数目安、診療単価目安
# 出典: 医療施設調査を基にした業界資料(二次資料)。DATA_SOURCES.md参照。
# 内科・整形外科は実データに近い値、それ以外は近似値(要:UIで明示)
# ============================================================
@dataclass
class DepartmentBenchmark:
    daily_patients_typical: int  # 平均的な診療所の1日患者数(需要が十分にある場合の目安)
    revenue_per_patient: int     # 1人あたり診療単価(円、院外処方想定)
    is_estimated: bool           # True: 内科/整形外科以外の推定値


DEPARTMENT_BENCHMARKS = {
    "内科": DepartmentBenchmark(daily_patients_typical=31, revenue_per_patient=5200, is_estimated=False),
    "整形外科": DepartmentBenchmark(daily_patients_typical=92, revenue_per_patient=4500, is_estimated=True),
    "小児科": DepartmentBenchmark(daily_patients_typical=31, revenue_per_patient=5000, is_estimated=True),
    "皮膚科": DepartmentBenchmark(daily_patients_typical=40, revenue_per_patient=4800, is_estimated=True),
    "耳鼻科": DepartmentBenchmark(daily_patients_typical=45, revenue_per_patient=4500, is_estimated=True),
    "歯科": DepartmentBenchmark(daily_patients_typical=20, revenue_per_patient=6500, is_estimated=True),
    "美容系": DepartmentBenchmark(daily_patients_typical=15, revenue_per_patient=15000, is_estimated=True),
}

MONTHLY_WORKING_DAYS = 24  # 月の診療日数の想定(週6日診療相当)


@dataclass
class StaffPlan:
    doctor_count: int = 1
    nurse_count: int = 1
    clerk_count: int = 1
    nurse_aide_count: int = 0
    medical_technician_count: int = 0


@dataclass
class BEPResult:
    department: str
    monthly_rent: int
    staff_plan: StaffPlan
    monthly_staff_cost: int
    monthly_fixed_cost: int
    revenue_per_patient: int
    breakeven_patients_per_day: float
    typical_patients_per_day: int
    is_department_estimated: bool


def calculate_monthly_staff_cost(staff_plan: StaffPlan) -> int:
    """スタッフ構成から月額人件費を算出する(実測の年間給与を12で割った近似)"""
    total_annual = (
        staff_plan.doctor_count * ANNUAL_SALARY["doctor"]
        + staff_plan.nurse_count * ANNUAL_SALARY["nurse"]
        + staff_plan.nurse_aide_count * ANNUAL_SALARY["nurse_aide"]
        + staff_plan.medical_technician_count * ANNUAL_SALARY["medical_technician"]
        + staff_plan.clerk_count * ANNUAL_SALARY["clerk"]
    )
    return round(total_annual / 12)


def calculate_bep(
    department: str,
    monthly_rent: int,
    staff_plan: StaffPlan,
    other_monthly_cost: int = 300_000,  # 光熱費・医療材料費等のその他固定費(概算)
) -> BEPResult:
    """損益分岐点診断を実行する

    注意: ここでは損益分岐点(供給側の採算ライン)のみを算出する。
    商圏の実際の需要規模との比較は、受療率データ等の裏付けが揃うまで
    意図的に行わない(競合数だけで需要を機械的に按分するのは実態を反映しないため)。
    利用者は本結果と、別途取得した商圏人口・競合数を並べて自身で判断する。
    """
    benchmark = DEPARTMENT_BENCHMARKS.get(department)
    if benchmark is None:
        raise ValueError(f"未対応の診療科です: {department}")

    monthly_staff_cost = calculate_monthly_staff_cost(staff_plan)
    monthly_fixed_cost = monthly_rent + monthly_staff_cost + other_monthly_cost

    # 損益分岐点患者数(1日あたり) = 月間固定費 / 診療単価 / 月間診療日数
    breakeven_patients_per_day = monthly_fixed_cost / benchmark.revenue_per_patient / MONTHLY_WORKING_DAYS

    return BEPResult(
        department=department,
        monthly_rent=monthly_rent,
        staff_plan=staff_plan,
        monthly_staff_cost=monthly_staff_cost,
        monthly_fixed_cost=monthly_fixed_cost,
        revenue_per_patient=benchmark.revenue_per_patient,
        breakeven_patients_per_day=round(breakeven_patients_per_day, 1),
        typical_patients_per_day=benchmark.daily_patients_typical,
        is_department_estimated=benchmark.is_estimated,
    )
