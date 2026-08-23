const apiStatus = document.querySelector("#api-status");
const dataStatus = document.querySelector("#data-status");
const routeStatus = document.querySelector("#route-status");
const routeSummary = document.querySelector("#route-summary");
const resetRouteButton = document.querySelector("#reset-route");
const map = L.map("map").setView([35.681236, 139.767125], 15);
let selectedPoints = [];
let selectedMarkers = [];
let routeLayer = null;

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
      interactive: false,
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

function addSelectedPoint(latlng) {
  if (selectedPoints.length === 2) {
    resetRoute();
  }

  selectedPoints.push(latlng);
  const isStart = selectedPoints.length === 1;
  const marker = L.circleMarker(latlng, {
    radius: 7,
    color: isStart ? "#1d4ed8" : "#dc2626",
    fillColor: isStart ? "#60a5fa" : "#f87171",
    fillOpacity: 1,
    weight: 2,
  })
    .bindTooltip(isStart ? "出発地点" : "目的地点")
    .addTo(map);
  selectedMarkers.push(marker);

  if (isStart) {
    routeStatus.textContent = "目的地点をクリックしてください。";
  } else {
    loadShortestRoute();
  }
}

async function loadShortestRoute() {
  const [start, end] = selectedPoints;
  routeStatus.textContent = "最短経路を計算しています。";
  routeSummary.hidden = true;

  const parameters = new URLSearchParams({
    start_lat: start.lat,
    start_lon: start.lng,
    end_lat: end.lat,
    end_lon: end.lng,
  });

  try {
    const response = await fetch(`/api/routes/shortest?${parameters}`);
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || `HTTP ${response.status}`);
    }

    if (routeLayer) {
      routeLayer.remove();
    }
    routeLayer = L.geoJSON(result.route, {
      style: { color: "#1d4ed8", weight: 6, opacity: 0.95 },
      interactive: false,
    }).addTo(map);
    showRouteSummary(result.summary);
    routeStatus.textContent = "距離最短ルートを表示しました。";
  } catch (error) {
    routeStatus.textContent = `経路計算に失敗しました: ${error.message}`;
    console.error("Shortest route request failed:", error);
  }
}

function showRouteSummary(summary) {
  document.querySelector("#metric-distance").textContent = formatDistance(
    summary.distance_m,
  );
  document.querySelector("#metric-edges").textContent =
    `${summary.edge_count}区間`;
  document.querySelector("#metric-major-road").textContent =
    `${summary.major_road_pct}%`;
  document.querySelector("#metric-cycleway").textContent =
    `${summary.cycleway_pct}%`;
  document.querySelector("#metric-signals").textContent =
    `${summary.traffic_signal_count}か所`;
  document.querySelector("#metric-maxspeed-unknown").textContent =
    `${summary.unknown_maxspeed_pct}%`;
  document.querySelector("#metric-width-unknown").textContent =
    `${summary.unknown_width_pct}%`;
  document.querySelector("#metric-surface-unknown").textContent =
    `${summary.unknown_surface_pct}%`;
  document.querySelector("#metric-provisional-cost").textContent =
    summary.provisional_cost === null ? "算出対象外" : summary.provisional_cost;
  routeSummary.hidden = false;
}

function formatDistance(distanceMeters) {
  if (distanceMeters >= 1000) {
    return `${(distanceMeters / 1000).toFixed(2)} km`;
  }
  return `${Math.round(distanceMeters)} m`;
}

function resetRoute() {
  selectedPoints = [];
  selectedMarkers.forEach((marker) => marker.remove());
  selectedMarkers = [];
  if (routeLayer) {
    routeLayer.remove();
    routeLayer = null;
  }
  routeSummary.hidden = true;
  routeStatus.textContent = "地図上で出発地点をクリックしてください。";
}

checkApi();
loadRoads();
map.on("click", (event) => addSelectedPoint(event.latlng));
resetRouteButton.addEventListener("click", resetRoute);
