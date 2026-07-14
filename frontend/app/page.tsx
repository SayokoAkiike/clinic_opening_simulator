"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { DEPARTMENTS, WALK_MINUTE_OPTIONS, type Department } from "@/lib/departments";

const ClinicMap = dynamic(() => import("@/components/ClinicMap"), { ssr: false });

type GeocodeResult = {
  title: string;
  address: string;
  latitude: number;
  longitude: number;
};

type AgeBracket = {
  age_bracket: string;
  male: number;
  female: number;
  total: number;
};

type DiagnosisResult = {
  catchment: {
    total_population: number;
    total_households: number;
    mesh_count: number;
    radius_m: number;
    age_breakdown: AgeBracket[];
    competitor_count: number;
  };
  bep: {
    monthly_rent: number;
    monthly_staff_cost: number;
    monthly_fixed_cost: number;
    revenue_per_patient: number;
    breakeven_patients_per_day: number;
    typical_patients_per_day: number;
    is_patient_count_estimated: boolean;
    is_revenue_estimated: boolean;
  };
  theoretical_demand: {
    has_rate_data: boolean;
    daily_patients_area_total: number;
    annual_patients_area_total: number;
  };
};

export default function Home() {
  const [addressQuery, setAddressQuery] = useState("");
  const [geoResults, setGeoResults] = useState<GeocodeResult[]>([]);
  const [selectedPlace, setSelectedPlace] = useState<GeocodeResult | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  const [department, setDepartment] = useState<Department>("内科");
  const [walkMinutes, setWalkMinutes] = useState(10);
  const [monthlyRent, setMonthlyRent] = useState(300000);
  const [doctorCount, setDoctorCount] = useState(1);
  const [nurseCount, setNurseCount] = useState(1);
  const [clerkCount, setClerkCount] = useState(1);

  const [result, setResult] = useState<DiagnosisResult | null>(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnosisError, setDiagnosisError] = useState<string | null>(null);

  async function handleSearchAddress() {
    if (!addressQuery.trim()) return;
    setGeoLoading(true);
    setGeoError(null);
    setGeoResults([]);
    setSelectedPlace(null);
    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(addressQuery)}`);
      const data = await res.json();
      if (!res.ok) {
        setGeoError(data.error ?? "住所検索に失敗しました。");
        return;
      }
      if (data.results.length === 0) {
        setGeoError("該当する住所が見つかりませんでした。町名や番地を変えてお試しください。");
        return;
      }
      setGeoResults(data.results);
      setSelectedPlace(data.results[0]);
    } catch {
      setGeoError("住所検索サーバーに接続できませんでした。");
    } finally {
      setGeoLoading(false);
    }
  }

  async function handleDiagnose() {
    if (!selectedPlace) {
      setDiagnosisError("先に開業予定地の住所を検索してください。");
      return;
    }
    setDiagnosing(true);
    setDiagnosisError(null);
    setResult(null);
    try {
      const res = await fetch("/api/diagnosis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          latitude: selectedPlace.latitude,
          longitude: selectedPlace.longitude,
          walkMinutes,
          department,
          monthlyRent,
          doctorCount,
          nurseCount,
          clerkCount,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setDiagnosisError(data.error ?? "診断に失敗しました。");
        return;
      }
      setResult(data);
    } catch {
      setDiagnosisError("診断サーバーに接続できませんでした。");
    } finally {
      setDiagnosing(false);
    }
  }

  const maxAgeTotal = useMemo(() => {
    if (!result) return 0;
    return Math.max(...result.catchment.age_breakdown.map((a) => a.total), 1);
  }, [result]);

  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <header className="mb-12">
          <p className="text-sm tracking-widest text-[var(--color-accent)] font-semibold mb-3">
            CLINIC OPENING SIMULATOR
          </p>
          <h1 className="font-display text-4xl md:text-5xl leading-tight mb-4">
            この場所、開業に向いていますか？
          </h1>
          <p className="text-[var(--color-ink-soft)] leading-relaxed">
            住所と開業条件を入れるだけで、商圏の人口・競合状況・損益分岐点を5分で確認できます。
          </p>
        </header>

        <section className="bg-white border border-[var(--color-border)] rounded-lg p-6 md:p-8 mb-10 shadow-sm">
          <div className="mb-6">
            <label className="block text-sm font-semibold mb-2">開業予定地の住所</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={addressQuery}
                onChange={(e) => setAddressQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearchAddress()}
                placeholder="例: 東京都千代田区丸の内1-9-1"
                className="flex-1 border border-[var(--color-border)] rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              />
              <button
                type="button"
                onClick={handleSearchAddress}
                disabled={geoLoading}
                className="px-4 py-2 rounded-md bg-[var(--color-accent)] text-white font-medium disabled:opacity-50"
              >
                {geoLoading ? "検索中…" : "検索"}
              </button>
            </div>
            {geoError && <p className="text-sm text-[var(--color-warn)] mt-2">{geoError}</p>}

            {geoResults.length > 1 && (
              <div className="mt-3 border border-[var(--color-border)] rounded-md divide-y">
                {geoResults.slice(0, 5).map((r) => (
                  <button
                    key={`${r.latitude}-${r.longitude}`}
                    type="button"
                    onClick={() => setSelectedPlace(r)}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-[var(--color-bg)] ${
                      selectedPlace?.title === r.title ? "bg-[var(--color-bg)] font-semibold" : ""
                    }`}
                  >
                    {r.title}
                  </button>
                ))}
              </div>
            )}

            {selectedPlace && (
              <div className="mt-4">
                <ClinicMap
                  latitude={selectedPlace.latitude}
                  longitude={selectedPlace.longitude}
                  radiusMeters={result?.catchment.radius_m}
                />
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <div>
              <label className="block text-sm font-semibold mb-2">診療科</label>
              <select
                value={department}
                onChange={(e) => setDepartment(e.target.value as Department)}
                className="w-full border border-[var(--color-border)] rounded-md px-3 py-2"
              >
                {DEPARTMENTS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold mb-2">駅・立地からの徒歩</label>
              <select
                value={walkMinutes}
                onChange={(e) => setWalkMinutes(Number(e.target.value))}
                className="w-full border border-[var(--color-border)] rounded-md px-3 py-2"
              >
                {WALK_MINUTE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-semibold mb-2">想定家賃(月額・円)</label>
              <input
                type="number"
                min={0}
                step={10000}
                value={monthlyRent}
                onChange={(e) => setMonthlyRent(Number(e.target.value))}
                className="w-full border border-[var(--color-border)] rounded-md px-3 py-2"
              />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-xs font-semibold mb-2">医師数</label>
                <input
                  type="number"
                  min={0}
                  value={doctorCount}
                  onChange={(e) => setDoctorCount(Number(e.target.value))}
                  className="w-full border border-[var(--color-border)] rounded-md px-2 py-2"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-2">看護師数</label>
                <input
                  type="number"
                  min={0}
                  value={nurseCount}
                  onChange={(e) => setNurseCount(Number(e.target.value))}
                  className="w-full border border-[var(--color-border)] rounded-md px-2 py-2"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-2">事務数</label>
                <input
                  type="number"
                  min={0}
                  value={clerkCount}
                  onChange={(e) => setClerkCount(Number(e.target.value))}
                  className="w-full border border-[var(--color-border)] rounded-md px-2 py-2"
                />
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={handleDiagnose}
            disabled={diagnosing}
            className="w-full py-3 rounded-md bg-[var(--color-ink)] text-white font-semibold disabled:opacity-50"
          >
            {diagnosing ? "診断中…" : "診断する"}
          </button>
          {diagnosisError && (
            <p className="text-sm text-[var(--color-warn)] mt-3">{diagnosisError}</p>
          )}
        </section>

        {result && (
          <section className="diagnosis-sheet">
            <div className="pt-2">
              <p className="text-xs tracking-widest text-[var(--color-ink-soft)]">診断シート</p>
              <h2 className="font-display text-2xl">
                {department} / {selectedPlace?.title}
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 my-6">
              <StatCard
                label="商圏人口"
                value={`${result.catchment.total_population.toLocaleString()}人`}
              />
              <StatCard label="商圏半径" value={`${Math.round(result.catchment.radius_m)}m`} />
              <StatCard
                label={`同科競合(${department})`}
                value={`${result.catchment.competitor_count}件`}
              />
            </div>

            <div className="border-t border-dashed border-[var(--color-border)] my-6" />

            <h3 className="font-semibold mb-3">損益分岐点</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <StatCard
                label="損益分岐点(1日あたり患者数)"
                value={`${result.bep.breakeven_patients_per_day}人`}
                accent
              />
              <StatCard
                label="同科の一般的な患者数(参考)"
                value={`${result.bep.typical_patients_per_day}人/日`}
              />
            </div>
            <div className="text-sm text-[var(--color-ink-soft)] space-y-1 mb-4">
              <p>
                月間固定費 {result.bep.monthly_fixed_cost.toLocaleString()}円 (家賃{" "}
                {result.bep.monthly_rent.toLocaleString()}円 + 人件費{" "}
                {result.bep.monthly_staff_cost.toLocaleString()}円 + その他)
              </p>
              <p>診療単価目安 {result.bep.revenue_per_patient.toLocaleString()}円/人</p>
            </div>

            <div className="flex flex-wrap gap-2 mb-4">
              {result.bep.is_patient_count_estimated && (
                <p className="inline-block text-xs px-2 py-1 rounded bg-[var(--color-warn-bg)] text-[var(--color-warn)]">
                  患者数は同系統の診療科をもとにした概算値です
                </p>
              )}
              {result.bep.is_revenue_estimated && (
                <p className="inline-block text-xs px-2 py-1 rounded bg-[var(--color-warn-bg)] text-[var(--color-warn)]">
                  診療単価は業界統計に基づく概算値です(公式統計に単価データなし)
                </p>
              )}
            </div>

            <div className="border-t border-dashed border-[var(--color-border)] my-6" />

            <h3 className="font-semibold mb-3">商圏全体の理論需要</h3>
            {result.theoretical_demand.has_rate_data ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-2">
                  <StatCard
                    label="商圏内の理論患者数(1日あたり)"
                    value={`${result.theoretical_demand.daily_patients_area_total}人`}
                  />
                  <StatCard
                    label="商圏内の理論患者数(年間)"
                    value={`${result.theoretical_demand.annual_patients_area_total.toLocaleString()}人`}
                  />
                </div>
                <p className="text-xs text-[var(--color-ink-soft)] mb-4">
                  厚生労働省「患者調査」の外来受療率と商圏内の年齢構成から算出した、この立地・診療科全体の理論的な需要規模です。同科競合{result.catchment.competitor_count}件と分け合うことになる点に留意してください。
                </p>
              </>
            ) : (
              <p className="text-xs text-[var(--color-ink-soft)] mb-4">
                {department}は公的統計(患者調査)の対象外のため、理論需要は算出していません。商圏人口・競合数を参考に判断してください。
              </p>
            )}

            <div className="border-t border-dashed border-[var(--color-border)] my-6" />

            <h3 className="font-semibold mb-3">年齢構成(商圏内)</h3>
            <div className="space-y-1 text-sm">
              {result.catchment.age_breakdown.map((a) => (
                <div key={a.age_bracket} className="flex items-center gap-2">
                  <span className="w-14 text-[var(--color-ink-soft)]">{a.age_bracket}</span>
                  <div className="flex-1 bg-[var(--color-bg)] rounded h-3 overflow-hidden">
                    <div
                      className="h-full bg-[var(--color-accent)]"
                      style={{ width: `${Math.min(100, (a.total / maxAgeTotal) * 100)}%` }}
                    />
                  </div>
                  <span className="w-12 text-right tabular-nums">{a.total}人</span>
                </div>
              ))}
            </div>

            <p className="text-xs text-[var(--color-ink-soft)] mt-8">
              出典: 総務省統計局「令和2年国勢調査」、厚生労働省「医療情報ネットのオープンデータ」、中央社会保険医療協議会「医療経済実態調査」ほか。詳細はDATA_SOURCES.mdを参照。本診断は公開統計に基づく参考情報であり、開業の成功を保証するものではありません。
            </p>
          </section>
        )}
      </div>
    </main>
  );
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-md border border-[var(--color-border)] p-4 ${
        accent ? "bg-[var(--color-accent)]/5" : "bg-white"
      }`}
    >
      <p className="text-xs text-[var(--color-ink-soft)] mb-1">{label}</p>
      <p className="font-display text-2xl tabular-nums">{value}</p>
    </div>
  );
}
