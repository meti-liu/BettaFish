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
const responseSimMeta = document.getElementById("responseSimMeta");
const responseSimProgress = document.getElementById("responseSimProgress");
const responseSimTimeline = document.getElementById("responseSimTimeline");
const responseSimChart = echarts.init(document.getElementById("responseSimChart"));

let boardItems = [];
const localState = new Map();
let runningTask = null;

function itemKey(x) {
  return `${x.platform || ""}|${x.topic_name || ""}`;
}

function getItemView(x) {
  const key = itemKey(x);
  const st = localState.get(key);
  if (!st) return { ...x };
  return {
    ...x,
    topic_ri: st.topic_ri,
    status: st.status,
    effect_drop: st.effect_drop,
  };
}

function responseBoardUrl() {
  const topic = (topicSelect?.value || topicInput.value).trim();
  return `/mvp/api/response-board?platform=${platformSelect.value}&topic=${encodeURIComponent(
    topic
  )}&theme=${encodeURIComponent((themeSelect?.value || "").trim())}&sub_theme=${encodeURIComponent(
    (subThemeSelect?.value || "").trim()
  )}&start_date=${startDateInput.value}&end_date=${endDateInput.value}&top_n=30&force_refresh=1`;
}

function renderBoard(items) {
  if (!items.length) {
    responseBoardBody.innerHTML = '<tr><td colspan="8">暂无数据</td></tr>';
    return;
  }
  responseBoardBody.innerHTML = items
    .map(
      (raw) => {
        const x = getItemView(raw);
        const key = itemKey(raw);
        const canRespond = true;
        const btnLabel = x.status === "已执行" ? "再次演练" : "执行响应";
        return `<tr>
      <td>${x.platform_label || x.platform}</td>
      <td>${x.topic_name || "-"}</td>
      <td><span class="risk-badge ${x.topic_ri >= 80 ? "risk-high" : x.topic_ri >= 50 ? "risk-mid" : "risk-low"}">${x.topic_ri}</span></td>
      <td>${x.status || "-"}</td>
      <td>${((x.attack_ratio || 0) * 100).toFixed(2)}%</td>
      <td class="content-ellipsis" title="${(x.measure || "").replace(/"/g, "&quot;")}">${x.measure || "-"}</td>
      <td>${x.effect_drop || 0}%</td>
      <td><button class="btn-primary respond-btn" data-key="${key}" ${canRespond ? "" : "disabled"}>${btnLabel}</button></td>
    </tr>`;
      }
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
  const top = [...items]
    .map(getItemView)
    .sort((a, b) => (b.effect_drop || 0) - (a.effect_drop || 0))
    .slice(0, 12);
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

function renderSimChart(points) {
  responseSimChart.setOption(
    {
      animationDuration: 260,
      tooltip: { trigger: "axis" },
      grid: { left: 42, right: 18, top: 24, bottom: 24 },
      xAxis: {
        type: "category",
        data: points.map((p) => p.step),
        axisLabel: { color: "#c3d0f2" },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { color: "#c3d0f2" },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
      },
      series: [
        {
          type: "line",
          smooth: true,
          showSymbol: true,
          symbolSize: 8,
          lineStyle: { width: 3, color: "#52d89c" },
          areaStyle: { color: "rgba(82,216,156,0.15)" },
          data: points.map((p) => p.ri),
        },
      ],
    },
    true
  );
}

function refreshBoardVisuals() {
  renderBoard(boardItems);
  const viewed = boardItems.map(getItemView);
  const counter = {};
  for (const x of viewed) {
    counter[x.status] = (counter[x.status] || 0) + 1;
  }
  const dist = Object.keys(counter).map((k) => ({ name: k, value: counter[k] }));
  renderStatusChart(dist);
  renderEffectChart(viewed);
}

function pushTimelineRow(text) {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  const row = document.createElement("div");
  row.className = "rank-item";
  row.innerHTML = `<div>${hh}:${mm}:${ss}</div><div>${text}</div>`;
  responseSimTimeline.prepend(row);
}

function runResponseSimulation(item) {
  if (!item) return;
  if (runningTask) clearInterval(runningTask);
  const key = itemKey(item);
  const startRi = Number(item.topic_ri || 0);
  const points = [
    { step: "预警触发", ri: startRi, status: "待处理", progress: 12, msg: "系统触发预警，进入人工复核。" },
    { step: "处置执行", ri: Math.max(0, startRi - 8), status: "处理中", progress: 45, msg: "发布澄清信息并清理高风险评论。" },
    { step: "扩散抑制", ri: Math.max(0, startRi - 15), status: "处理中", progress: 72, msg: "关键词限流生效，攻击占比下降。" },
    { step: "闭环完成", ri: Math.max(0, startRi - 22), status: "已执行", progress: 100, msg: "风险回落，形成闭环记录。" },
  ];

  responseSimMeta.textContent = `演示事件：${item.topic_name}（${item.platform_label || item.platform}）`;
  responseSimTimeline.innerHTML = "";
  renderSimChart([points[0]]);
  responseSimProgress.style.width = `${points[0].progress}%`;
  pushTimelineRow(points[0].msg);

  let idx = 0;
  runningTask = setInterval(() => {
    idx += 1;
    if (idx >= points.length) {
      clearInterval(runningTask);
      runningTask = null;
      return;
    }
    const p = points[idx];
    localState.set(key, {
      topic_ri: Number(p.ri.toFixed(2)),
      status: p.status,
      effect_drop: Number(Math.max(0, ((startRi - p.ri) / Math.max(1, startRi)) * 100).toFixed(1)),
    });
    responseSimProgress.style.width = `${p.progress}%`;
    pushTimelineRow(p.msg);
    renderSimChart(points.slice(0, idx + 1));
    refreshBoardVisuals();
  }, 1000);
}

async function loadResponseBoard() {
  responseBoardBody.innerHTML = '<tr><td colspan="8"><div class="skeleton"></div></td></tr>';
  try {
    const res = await apiGet(responseBoardUrl());
    boardItems = res.data?.items || [];
    localState.clear();
    refreshBoardVisuals();
    responseSimMeta.textContent = "点击上方“执行响应”按钮查看动态过程";
    responseSimProgress.style.width = "0%";
    responseSimTimeline.innerHTML = "";
    renderSimChart([]);
  } catch (err) {
    responseBoardBody.innerHTML = `<tr><td colspan="8">加载失败：${err.message}</td></tr>`;
    statusChart.setOption({ title: { text: `加载失败: ${err.message}`, left: "center", textStyle: { color: "#fff" } } }, true);
    effectChart.setOption({ title: { text: `加载失败: ${err.message}`, left: "center", textStyle: { color: "#fff" } } }, true);
  }
}

window.addEventListener("resize", () => {
  statusChart.resize();
  effectChart.resize();
  responseSimChart.resize();
});
loadResponseBoardBtn.addEventListener("click", loadResponseBoard);
topicSelect?.addEventListener("change", () => {
  if (topicSelect.value) topicInput.value = topicSelect.value;
});
responseBoardBody.addEventListener("click", (e) => {
  const btn = e.target.closest(".respond-btn");
  if (!btn) return;
  const key = btn.getAttribute("data-key");
  const item = boardItems.find((x) => itemKey(x) === key);
  runResponseSimulation(item);
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
