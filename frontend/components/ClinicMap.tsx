"use client";

import { MapContainer, TileLayer, Marker, Circle } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";

// Leafletのデフォルトマーカーアイコンはバンドラー環境でパスが壊れるため明示的に再設定する
const markerIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

type Props = {
  latitude: number;
  longitude: number;
  radiusMeters?: number;
};

export default function ClinicMap({ latitude, longitude, radiusMeters }: Props) {
  return (
    <MapContainer
      center={[latitude, longitude]}
      zoom={16}
      scrollWheelZoom={false}
      style={{ height: "280px", width: "100%", borderRadius: "8px" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Marker position={[latitude, longitude]} icon={markerIcon} />
      {radiusMeters ? (
        <Circle
          center={[latitude, longitude]}
          radius={radiusMeters}
          pathOptions={{ color: "#0B5D52", fillColor: "#0B5D52", fillOpacity: 0.08 }}
        />
      ) : null}
    </MapContainer>
  );
}
