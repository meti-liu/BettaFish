const platformSelect = document.getElementById("platformSelect");
const themeSelect = document.getElementById("themeSelect");
const subThemeSelect = document.getElementById("subThemeSelect");
const topicSelect = document.getElementById("topicSelect");
const topicInput = document.getElementById("topicInput");
const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");
const loadResponseBoardBtn = document.getElementById("loadResponseBoardBtn");
const responseBoardBody = document.getElementById("responseBoardBody");
const statusChart = echarts.init(document.getElementById("statusChart"));
const effectChart = echarts.init(document.getElementById("effectChart"));

function responseBoardUrl() {
  const topic = (topicSelect?.value || topicInput.value).trim();
  return `/mvp/api/response-board?platform=${platformSelect.value}&topic=${encodeURIComponent(
    topic
  )}&theme=${encodeURIComponent((themeSelect?.value || "").trim())}&sub_theme=${encodeURIComponent(
    (subThemeSelect?.value || "").trim()
  )}&start_date=${startDateInput.value}&end_date=${endDateInput.value}&top_n=30`;
}

function renderBoard(items) {
  if (!items.length) {
    responseBoardBody.innerHTML = '<tr><td colspan="7">暂无数据</td></tr>';
    return;
  }
  responseBoardBody.innerHTML = items
    .map(
      (x) => `<tr>
      <td>${x.platform_label || x.platform}</td>
      <td>${x.topic_name || "-"}</td>
      <td><span class="risk-badge ${x.topic_ri >= 80 ? "risk-high" : x.topic_ri >= 50 ? "risk-mid" : "risk-low"}">${x.topic_ri}</span></td>
      <td>${x.status || "-"}</td>
      <td>${((x.attack_ratio || 0) * 100).toFixed(2)}%</td>
      <td class="content-ellipsis" title="${(x.measure || "").replace(/"/g, "&quot;")}">${x.measure || "-"}</td>
      <td>${x.effect_drop || 0}%</td>
    </tr>`
    )
    .join("");
}

function renderStatusChart(dist) {
  statusChart.setOption(
    {
      animationDuration: 280,
      tooltip: { trigger: "item" },
      legend: { bottom: 0, textStyle: { color: "#c3d0f2" } },
      series: [
        {
          type: "pie",
          radius: ["40%", "72%"],
          data: dist || [],
          label: { color: "#e8eefc" },
        },
      ],
    },
    true
  );
}

function renderEffectChart(items) {
  const top = [...items].sort((a, b) => (b.effect_drop || 0) - (a.effect_drop || 0)).slice(0, 12);
  effectChart.setOption(
    {
      animationDuration: 300,
      tooltip: { trigger: "axis" },
      grid: { left: 180, right: 20, top: 20, bottom: 20 },
      xAxis: {
        type: "value",
        axisLabel: { color: "#c3d0f2" },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
      },
      yAxis: {
        type: "category",
        axisLabel: { color: "#c3d0f2", width: 160, overflow: "truncate" },
        data: top.map((x) => `${x.platform_label}|${x.topic_name}`).reverse(),
      },
      series: [
        {
          type: "bar",
          data: top.map((x) => x.effect_drop || 0).reverse(),
          itemStyle: { color: "#52d89c" },
          label: { show: true, position: "right", color: "#e8eefc", formatter: "{c}%" },
        },
      ],
    },
    true
  );
}

async function loadResponseBoard() {
  responseBoardBody.innerHTML = '<tr><td colspan="7"><div class="skeleton"></div></td></tr>';
  try {
    const res = await apiGet(responseBoardUrl());
    const items = res.data?.items || [];
    renderBoard(items);
    renderStatusChart(res.data?.status_distribution || []);
    renderEffectChart(items);
  } catch (err) {
    responseBoardBody.innerHTML = `<tr><td colspan="7">加载失败：${err.message}</td></tr>`;
    statusChart.setOption({ title: { text: `加载失败: ${err.message}`, left: "center", textStyle: { color: "#fff" } } }, true);
    effectChart.setOption({ title: { text: `加载失败: ${err.message}`, left: "center", textStyle: { color: "#fff" } } }, true);
  }
}

window.addEventListener("resize", () => {
  statusChart.resize();
  effectChart.resize();
});
loadResponseBoardBtn.addEventListener("click", loadResponseBoard);
topicSelect?.addEventListener("change", () => {
  if (topicSelect.value) topicInput.value = topicSelect.value;
});

async function refreshTopicSelectors(resetDependent = true) {
  const opts = await loadTopicOptions({
    platform: platformSelect.value,
    startDate: startDateInput.value,
    endDate: endDateInput.value,
    theme: (themeSelect?.value || "").trim(),
    subTheme: (subThemeSelect?.value || "").trim(),
  });
  fillSelectOptions(themeSelect, opts.themes || [], "全部一级主题");
  fillSelectOptions(subThemeSelect, opts.sub_themes || [], "全部次主题");
  fillSelectOptions(topicSelect, opts.topics || [], "可选话题（不选则手输）");
  if (resetDependent) topicInput.value = "";
}

platformSelect.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
  loadResponseBoard();
});
themeSelect?.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
  loadResponseBoard();
});
subThemeSelect?.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
  loadResponseBoard();
});
startDateInput.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});
endDateInput.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});
formatDateInputDefaults(startDateInput, endDateInput, 30);
refreshTopicSelectors(true).then(loadResponseBoard);
