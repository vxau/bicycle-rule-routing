const apiStatus = document.querySelector("#api-status");
const dataStatus = document.querySelector("#data-status");
const map = L.map("map").setView([35.681236, 139.767125], 15);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

async function checkApi() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const result = await response.json();
    apiStatus.textContent = result.status === "ok" ? "接続済み" : "異常";
  } catch (error) {
    apiStatus.textContent = "接続できません";
    console.error("Health API check failed:", error);
  }
}

async function loadRoads() {
  try {
    const response = await fetch("/data/sample_edges.geojson");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const geojson = await response.json();
    const layer = L.geoJSON(geojson, {
      style: { color: "#256f4a", weight: 3, opacity: 0.8 },
    }).addTo(map);
    if (layer.getBounds().isValid()) {
      map.fitBounds(layer.getBounds());
    }
    dataStatus.textContent = `${geojson.features.length}区間を表示`;
  } catch (error) {
    dataStatus.textContent =
      "未生成（OSM取得スクリプトを実行してください）";
    console.warn("Road GeoJSON is not available:", error);
  }
}

checkApi();
loadRoads();
