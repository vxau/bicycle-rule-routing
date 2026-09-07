const apiStatus = document.querySelector("#api-status");
const dataStatus = document.querySelector("#data-status");
const routeStatus = document.querySelector("#route-status");
const routeSummary = document.querySelector("#route-summary");
const resetRouteButton = document.querySelector("#reset-route");
const profileLegend = document.querySelector("#profile-legend");
const routeComparison = document.querySelector("#route-comparison");
const routeComparisonBody = document.querySelector("#route-comparison-body");
const map = L.map("map").setView([35.681236, 139.767125], 15);
let selectedPoints = [];
let selectedMarkers = [];
let routeLayers = new Map();
let routeResults = [];
let activeRouteRequest = null;

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
    loadProfileRoutes();
  }
}

async function loadProfileRoutes() {
  const [start, end] = selectedPoints;
  if (activeRouteRequest) {
    activeRouteRequest.abort();
  }
  const request = new AbortController();
  activeRouteRequest = request;
  routeStatus.textContent = "5種類のルートを計算しています。";
  routeSummary.hidden = true;
  routeComparison.hidden = true;
  profileLegend.replaceChildren();

  const parameters = new URLSearchParams({
    start_lat: start.lat,
    start_lon: start.lng,
    end_lat: end.lat,
    end_lon: end.lng,
  });

  try {
    const response = await fetch(`/api/routes/compare?${parameters}`, {
      signal: request.signal,
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || `HTTP ${response.status}`);
    }

    if (activeRouteRequest === request) {
      renderRouteComparison(result.routes);
    }
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    routeStatus.textContent = `経路計算に失敗しました: ${error.message}`;
    console.error("Route comparison request failed:", error);
  } finally {
    if (activeRouteRequest === request) {
      activeRouteRequest = null;
    }
  }
}

function renderRouteComparison(routes) {
  clearRouteLayers();
  routeResults = routes;
  routeComparisonBody.replaceChildren();
  profileLegend.replaceChildren();

  routes.forEach((result) => {
    addLegendItem(result.profile);
    addComparisonRow(result);
    if (!result.available) {
      return;
    }
    const layer = L.geoJSON(result.route, {
      bubblingMouseEvents: false,
      style: {
        color: result.profile.color,
        weight: 4,
        opacity: 0.55,
      },
    })
      .bindTooltip(result.profile.label)
      .addTo(map);
    layer.on("click", (event) => {
      if (event.originalEvent) {
        L.DomEvent.stopPropagation(event.originalEvent);
      }
      focusRoute(result.profile.id);
    });
    routeLayers.set(result.profile.id, layer);
  });

  routeComparison.hidden = false;
  const preferred = routes.find(
    (result) => result.available && result.profile.id === "balanced",
  );
  const initial = preferred || routes.find((result) => result.available);
  if (initial) {
    focusRoute(initial.profile.id);
    routeStatus.textContent =
      `${routes.filter((result) => result.available).length}種類を計算しました。表の行を選ぶと強調表示します。`;
  } else {
    routeStatus.textContent = "利用できるルートがありません。";
  }
}

function addLegendItem(profile) {
  const item = document.createElement("span");
  item.className = "legend-item";
  const swatch = document.createElement("span");
  swatch.className = "legend-swatch";
  swatch.style.backgroundColor = profile.color;
  item.append(swatch, document.createTextNode(profile.label));
  profileLegend.append(item);
}

function addComparisonRow(result) {
  const row = document.createElement("tr");
  row.dataset.profileId = result.profile.id;
  const values = result.available
    ? [
        result.profile.label,
        formatDistance(result.summary.distance_m),
        `${result.summary.major_road_pct}%`,
        `${result.summary.cycleway_pct}%`,
        `${result.summary.unknown_attribute_pct}%`,
        result.summary.profile_cost,
      ]
    : [result.profile.label, "経路なし", "-", "-", "-", "-"];

  values.forEach((value) => {
    const cell = document.createElement("td");
    cell.textContent = value;
    row.append(cell);
  });

  if (result.available) {
    row.tabIndex = 0;
    row.addEventListener("click", () => focusRoute(result.profile.id));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        focusRoute(result.profile.id);
      }
    });
  } else {
    row.className = "unavailable";
  }
  routeComparisonBody.append(row);
}

function focusRoute(profileId) {
  routeLayers.forEach((layer, id) => {
    layer.setStyle({
      weight: id === profileId ? 7 : 3,
      opacity: id === profileId ? 0.95 : 0.2,
    });
    if (id === profileId) {
      layer.bringToFront();
    }
  });

  routeComparisonBody.querySelectorAll("tr").forEach((row) => {
    row.classList.toggle("selected", row.dataset.profileId === profileId);
  });
  const selected = routeResults.find(
    (result) => result.available && result.profile.id === profileId,
  );
  if (selected) {
    showRouteSummary(selected.summary, selected.profile);
  }
}

function showRouteSummary(summary, profile) {
  document.querySelector("#metric-profile").textContent = profile.label;
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
  document.querySelector("#metric-profile-cost").textContent =
    summary.profile_cost === null ? "算出対象外" : summary.profile_cost;
  routeSummary.hidden = false;
}

function clearRouteLayers() {
  routeLayers.forEach((layer) => layer.remove());
  routeLayers = new Map();
}

function formatDistance(distanceMeters) {
  if (distanceMeters >= 1000) {
    return `${(distanceMeters / 1000).toFixed(2)} km`;
  }
  return `${Math.round(distanceMeters)} m`;
}

function resetRoute() {
  if (activeRouteRequest) {
    activeRouteRequest.abort();
    activeRouteRequest = null;
  }
  selectedPoints = [];
  selectedMarkers.forEach((marker) => marker.remove());
  selectedMarkers = [];
  clearRouteLayers();
  routeResults = [];
  routeComparisonBody.replaceChildren();
  profileLegend.replaceChildren();
  routeComparison.hidden = true;
  routeSummary.hidden = true;
  routeStatus.textContent = "地図上で出発地点をクリックしてください。";
}

checkApi();
loadRoads();
map.on("click", (event) => addSelectedPoint(event.latlng));
resetRouteButton.addEventListener("click", resetRoute);
