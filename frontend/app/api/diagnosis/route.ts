import { NextRequest, NextResponse } from "next/server";

// FastAPIバックエンドはコンテナ内のlocalhostでのみ待ち受けているため、
// ブラウザから直接は呼べない。Next.jsのサーバー側(ここ)からのみ到達可能。
const BACKEND_BASE = process.env.BACKEND_API_BASE_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const {
    latitude,
    longitude,
    walkMinutes,
    department,
    monthlyRent,
    doctorCount,
    nurseCount,
    clerkCount,
  } = body;

  const catchmentParams = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    walk_minutes: String(walkMinutes),
    department,
  });

  const bepParams = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    walk_minutes: String(walkMinutes),
    department,
    monthly_rent: String(monthlyRent),
    doctor_count: String(doctorCount),
    nurse_count: String(nurseCount),
    clerk_count: String(clerkCount),
  });

  try {
    const [catchmentRes, bepRes] = await Promise.all([
      fetch(`${BACKEND_BASE}/api/catchment-analysis?${catchmentParams.toString()}`),
      fetch(`${BACKEND_BASE}/api/bep-diagnosis?${bepParams.toString()}`),
    ]);

    if (!catchmentRes.ok || !bepRes.ok) {
      return NextResponse.json(
        { error: "診断データの取得に失敗しました。しばらくしてから再度お試しください。" },
        { status: 502 }
      );
    }

    const [catchment, bepWrapped] = await Promise.all([
      catchmentRes.json(),
      bepRes.json(),
    ]);

    return NextResponse.json({ catchment, bep: bepWrapped.bep });
  } catch {
    return NextResponse.json(
      { error: "バックエンドに接続できませんでした。" },
      { status: 502 }
    );
  }
}
