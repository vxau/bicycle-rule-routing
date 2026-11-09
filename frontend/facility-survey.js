/* Facility inventory and a local, exportable list for field verification. */
(function (root) {
  "use strict";
  const STATES = {
    present: { label: "設備あり", color: "#16754a" },
    explicit_absent: { label: "明示的になし", color: "#be343e" },
    unknown: { label: "不明", color: "#596579", dashArray: "5 5" },
  };
  const STORAGE_KEY = "bicycle-facility-survey-v1";

  function csvCell(value) {
    let text = value == null ? "" : String(value);
    if (typeof value === "string" && (/^\s*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text))) {
      text = "'" + text;
    }
    return '"' + text.replaceAll('"', '""') + '"';
  }

  function toCsv(properties, datasetId) {
    const rows = [[
      "データ識別子", "区間ID", "道路名", "OSM判定", "延長_m",
      "始点緯度", "始点経度", "終点緯度", "終点経度", "方向別OSMタグ",
      "確認結果", "確認日", "根拠・資料URL", "幅員_m", "メモ",
    ]];
    properties.forEach(p => rows.push([
      datasetId, p.segment_id, p.name, STATES[p.facility_state].label, p.length_m,
      p.start_lat, p.start_lon, p.end_lat, p.end_lon, JSON.stringify(p.directions),
      "", "", "", "", "",
    ]));
    return "\uFEFF" + rows.map(row => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
  }

  function restoreSelection(raw, datasetId, availableIds) {
    try {
      const saved = JSON.parse(raw);
      if (!saved || !Array.isArray(saved.ids) || typeof saved.datasetId !== "string") {
        return { ids: [], stale: false };
      }
      if (saved.datasetId !== datasetId) return { ids: [], stale: saved.ids.length > 0 };
      const available = new Set(availableIds);
      return { ids: [...new Set(saved.ids.filter(id => available.has(id)))], stale: false };
    } catch {
      return { ids: [], stale: false };
    }
  }

  function create({ map }) {
    const status = document.querySelector("#survey-status");
    const storageStatus = document.querySelector("#survey-storage-status");
    const selectedList = document.querySelector("#survey-selected-list");
    const exportButton = document.querySelector("#survey-export");
    const retryButton = document.querySelector("#survey-retry");
    const filters = [...document.querySelectorAll("[data-facility-filter]")];
    const features = new Map();
    const roadLayers = new Map();
    const groups = new Map();
    let selected = new Set();
    let datasetId = null;
    let inventory = null;
    let active = false;
    let loading = false;

    function distance(value) {
      return value >= 1000 ? `${(value / 1000).toFixed(2)} km` : `${Math.round(value)} m`;
    }

    function style(p) {
      const state = STATES[p.facility_state];
      return {
        color: state.color, dashArray: state.dashArray || null,
        weight: selected.has(p.segment_id) ? 7 : 3,
        opacity: selected.has(p.segment_id) ? 1 : 0.8,
        className: `facility-road facility-state-${p.facility_state}`,
      };
    }

    function saveSelection() {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ datasetId, ids: [...selected] }));
        storageStatus.textContent = "選択はこのブラウザに保存されます。調査にはCSVも保存してください。";
      } catch {
        storageStatus.textContent = "ブラウザへ保存できません。ページを閉じる前にCSVを保存してください。";
      }
    }

    function toggleSelection(id) {
      if (selected.has(id)) selected.delete(id);
      else selected.add(id);
      roadLayers.get(id).setStyle(style(features.get(id).properties));
      saveSelection();
      renderSelection();
    }

    function renderSelection() {
      selectedList.replaceChildren();
      document.querySelector("#survey-selected-count").textContent = `${selected.size}区間`;
      document.querySelector("#survey-empty-selection").hidden = selected.size > 0;
      exportButton.disabled = selected.size === 0;
      selected.forEach(id => {
        const p = features.get(id).properties;
        const item = document.createElement("li");
        const locate = document.createElement("button");
        locate.type = "button";
        locate.className = "survey-locate";
        locate.textContent = `${p.name || "名称未登録"} · ${STATES[p.facility_state].label} · ${distance(p.length_m)}`;
        locate.title = `区間 ${id} を地図で確認`;
        locate.addEventListener("click", () => {
          const filter = filters.find(input => input.dataset.facilityFilter === p.facility_state);
          filter.checked = true;
          updateVisibility();
          const layer = roadLayers.get(id);
          map.fitBounds(layer.getBounds(), { maxZoom: 18, padding: [30, 30] });
          layer.openPopup();
        });
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "削除";
        remove.setAttribute("aria-label", "調査リストから削除");
        remove.addEventListener("click", () => {
          toggleSelection(id);
          map.closePopup();
        });
        item.append(locate, remove);
        selectedList.append(item);
      });
    }

    function popup(p) {
      const box = document.createElement("div");
      box.className = "survey-popup";
      const title = document.createElement("strong");
      title.textContent = p.name || "名称未登録";
      box.append(title);
      const description = document.createElement("p");
      description.textContent = `${STATES[p.facility_state].label}（OSM判定） · ${distance(p.length_m)}`;
      box.append(description);
      const identity = document.createElement("p");
      identity.textContent = `区間ID: ${p.segment_id}`;
      box.append(identity);
      if (p.direction_conflict) {
        const conflict = document.createElement("p");
        conflict.textContent = "方向によって判定が異なります。両方向の状況を確認してください。";
        box.append(conflict);
      }
      p.directions.forEach(direction => {
        const detail = document.createElement("details");
        const heading = document.createElement("summary");
        heading.textContent = `${direction.u} → ${direction.v} のタグ`;
        detail.append(heading);
        const tags = document.createElement("dl");
        Object.entries(direction.tags).forEach(([name, values]) => {
          const dt = document.createElement("dt");
          dt.textContent = name;
          const dd = document.createElement("dd");
          dd.textContent = values.length ? values.join(", ") : "未記録";
          tags.append(dt, dd);
        });
        if (direction.osm_ids.length) {
          const dt = document.createElement("dt");
          dt.textContent = "OSM way ID";
          const dd = document.createElement("dd");
          dd.textContent = direction.osm_ids.join(", ");
          tags.append(dt, dd);
        }
        detail.append(tags);
        box.append(detail);
      });
      const button = document.createElement("button");
      button.type = "button";
      function updateLabel() {
        button.textContent = selected.has(p.segment_id) ? "調査リストから外す" : "調査リストに追加";
      }
      updateLabel();
      button.addEventListener("click", event => {
        event.stopPropagation();
        toggleSelection(p.segment_id);
        updateLabel();
      });
      box.append(button);
      L.DomEvent.disableClickPropagation(box);
      L.DomEvent.disableScrollPropagation(box);
      return box;
    }

    function updateVisibility() {
      let visibleCount = 0;
      filters.forEach(input => {
        const state = input.dataset.facilityFilter;
        const group = groups.get(state);
        if (!group) return;
        if (active && input.checked) group.addTo(map);
        else group.remove();
        if (input.checked) visibleCount += inventory.summary.states[state].segment_count;
      });
      if (inventory) status.textContent = `${inventory.summary.segment_count}区間中 ${visibleCount}区間を表示`;
    }

    async function load() {
      if (loading || inventory) return;
      loading = true;
      status.textContent = "設備情報を読み込み中";
      retryButton.hidden = true;
      try {
        const response = await fetch("/api/facilities");
        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.detail || `HTTP ${response.status}`);
        }
        const result = await response.json();
        datasetId = result.dataset_id;
        result.features.forEach(feature => features.set(feature.properties.segment_id, feature));
        try {
          const restored = restoreSelection(localStorage.getItem(STORAGE_KEY), datasetId, features.keys());
          selected = new Set(restored.ids);
          storageStatus.textContent = restored.stale
            ? "道路データが変わりました。前の選択は復元せず、調査対象を選び直してください。"
            : "選択はこのブラウザに保存されます。調査にはCSVも保存してください。";
        } catch {
          storageStatus.textContent = "ブラウザ保存を利用できません。調査対象はCSVに保存してください。";
        }
        Object.keys(STATES).forEach(state => {
          const group = L.geoJSON(result.features.filter(f => f.properties.facility_state === state), {
            bubblingMouseEvents: false,
            style: feature => style(feature.properties),
            onEachFeature: (feature, layer) => {
              const id = feature.properties.segment_id;
              roadLayers.set(id, layer);
              layer.bindPopup(() => popup(feature.properties), { maxWidth: 320 });
              const tooltip = document.createElement("span");
              tooltip.textContent = `${STATES[state].label} · ${feature.properties.name || "名称未登録"}`;
              layer.bindTooltip(tooltip);
              layer.on("add", () => layer.getElement()?.setAttribute("data-segment-id", id));
            },
          });
          groups.set(state, group);
          const row = result.summary.states[state];
          document.querySelector(`[data-facility-count="${state}"]`).textContent =
            `${row.segment_count}区間 · ${distance(row.length_m)}`;
        });
        inventory = result;
        renderSelection();
        updateVisibility();
        if (active && result.features.length) {
          const bounds = L.latLngBounds([]);
          groups.forEach(group => { if (group.getBounds().isValid()) bounds.extend(group.getBounds()); });
          if (bounds.isValid()) map.fitBounds(bounds, { padding: [20, 20] });
        }
      } catch (error) {
        status.textContent = `設備情報を表示できません: ${error.message}`;
        retryButton.hidden = false;
      } finally {
        loading = false;
      }
    }

    filters.forEach(input => input.addEventListener("change", () => {
      map.closePopup();
      updateVisibility();
    }));
    retryButton.addEventListener("click", load);
    exportButton.addEventListener("click", () => {
      if (!selected.size) return;
      const csv = toCsv([...selected].map(id => features.get(id).properties), datasetId);
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "facility_survey.csv";
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });

    return {
      setActive(value) {
        active = value;
        map.closePopup();
        updateVisibility();
        if (active) load();
      },
    };
  }

  root.FacilitySurvey = { create, csvCell, toCsv, restoreSelection };
})(globalThis);
