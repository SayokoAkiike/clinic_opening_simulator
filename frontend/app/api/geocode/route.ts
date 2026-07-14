import { NextRequest, NextResponse } from "next/server";

// 国土地理院 住所検索API(無料・キー不要)をサーバー側からプロキシする。
// ブラウザから直接叩かない理由: CORS/レート制限の影響を受けにくくし、
// 将来別ジオコーダーに差し替える際もフロント側の変更を不要にするため。
export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q");
  if (!q) {
    return NextResponse.json({ error: "住所を入力してください。" }, { status: 400 });
  }

  try {
    const res = await fetch(
      `https://msearch.gsi.go.jp/address-search/AddressSearch?q=${encodeURIComponent(q)}`
    );
    if (!res.ok) {
      return NextResponse.json({ error: "住所検索に失敗しました。" }, { status: 502 });
    }
    const data = (await res.json()) as Array<{
      geometry: { coordinates: [number, number] };
      properties: { title: string; addr?: string };
    }>;

    const results = data.map((item) => ({
      title: item.properties.title,
      address: item.properties.addr ?? item.properties.title,
      longitude: item.geometry.coordinates[0],
      latitude: item.geometry.coordinates[1],
    }));

    return NextResponse.json({ results });
  } catch {
    return NextResponse.json(
      { error: "住所検索サーバーに接続できませんでした。" },
      { status: 502 }
    );
  }
}
