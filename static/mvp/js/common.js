function formatDateInputDefaults(startInput, endInput, days = 30) {
  const endDate = new Date();
  const startDate = new Date();
  startDate.setDate(endDate.getDate() - (days - 1));

  const toDateString = (d) => d.toISOString().slice(0, 10);
  if (startInput && !startInput.value) startInput.value = toDateString(startDate);
  if (endInput && !endInput.value) endInput.value = toDateString(endDate);
}

function showSkeleton(container, rows = 4) {
  if (!container) return;
  container.innerHTML = "";
  for (let i = 0; i < rows; i += 1) {
    const div = document.createElement("div");
    div.className = "skeleton";
    container.appendChild(div);
  }
}

async function apiGet(url) {
  const sep = url.includes("?") ? "&" : "?";
  const noCacheUrl = `${url}${sep}_ts=${Date.now()}`;
  const res = await fetch(noCacheUrl, {
    cache: "no-store",
    headers: {
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
    },
  });
  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.message || "请求失败");
  }
  return data;
}

function fillSelectOptions(selectEl, items, placeholder) {
  if (!selectEl) return;
  const prev = selectEl.value || "";
  const opts = [`<option value="">${placeholder}</option>`]
    .concat((items || []).map((x) => `<option value="${String(x).replace(/"/g, "&quot;")}">${x}</option>`))
    .join("");
  selectEl.innerHTML = opts;
  const hasPrev = (items || []).includes(prev);
  selectEl.value = hasPrev ? prev : "";
}

async function loadTopicOptions({ platform, startDate, endDate, theme = "", subTheme = "" }) {
  const url = `/mvp/api/topic-options?platform=${encodeURIComponent(platform)}&start_date=${encodeURIComponent(
    startDate || ""
  )}&end_date=${encodeURIComponent(endDate || "")}&theme=${encodeURIComponent(theme)}&sub_theme=${encodeURIComponent(subTheme)}`;
  const res = await apiGet(url);
  return res.data || { themes: [], sub_themes: [], topics: [] };
}
