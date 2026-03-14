const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");
const platformSelect = document.getElementById("platformSelect");
const mapModeSelect = document.getElementById("mapModeSelect");
const mapModeRiskBtn = document.getElementById("mapModeRiskBtn");
const mapModeHeatBtn = document.getElementById("mapModeHeatBtn");
const mapModeHint = document.getElementById("mapModeHint");
const themeSelect = document.getElementById("themeSelect");
const subThemeSelect = document.getElementById("subThemeSelect");
const topicSelect = document.getElementById("topicSelect");
const topicInput = document.getElementById("topicInput");
const loadHeatmapBtn = document.getElementById("loadHeatmapBtn");
const regionList = document.getElementById("regionList");
const hotTopicList = document.getElementById("hotTopicList");
const provinceDetailList = document.getElementById("provinceDetailList");
const provinceDetailTitle = document.getElementById("provinceDetailTitle");
const regionPrevPageBtn = document.getElementById("regionPrevPage");
const regionNextPageBtn = document.getElementById("regionNextPage");
const regionPageInfo = document.getElementById("regionPageInfo");
const mapChart = echarts.init(document.getElementById("chinaMap"));
const trendChart = echarts.init(document.getElementById("heatTrendChart"));
const totalEventsEl = document.getElementById("totalEvents");
const provinceCountEl = document.getElementById("provinceCount");
const highRiskProvincesEl = document.getElementById("highRiskProvinces");
const peakHeatProvinceEl = document.getElementById("peakHeatProvince");
const peakRiskProvinceEl = document.getElementById("peakRiskProvince");

let chinaMapLoaded = false;
let currentMapData = [];
let currentSummary = null;
let selectedProvince = "";
let regionCurrentPage = 1;
let regionTotalPages = 1;
const PROVINCE_FULLNAME_MAP = {
  北京: "北京市",
  天津: "天津市",
  上海: "上海市",
  重庆: "重庆市",
  河北: "河北省",
  山西: "山西省",
  辽宁: "辽宁省",
  吉林: "吉林省",
  黑龙江: "黑龙江省",
  江苏: "江苏省",
  浙江: "浙江省",
  安徽: "安徽省",
  福建: "福建省",
  江西: "江西省",
  山东: "山东省",
  河南: "河南省",
  湖北: "湖北省",
  湖南: "湖南省",
  广东: "广东省",
  海南: "海南省",
  四川: "四川省",
  贵州: "贵州省",
  云南: "云南省",
  陕西: "陕西省",
  甘肃: "甘肃省",
  青海: "青海省",
  台湾: "台湾省",
  内蒙古: "内蒙古自治区",
  广西: "广西壮族自治区",
  西藏: "西藏自治区",
  宁夏: "宁夏回族自治区",
  新疆: "新疆维吾尔自治区",
  香港: "香港特别行政区",
  澳门: "澳门特别行政区",
};
const PROVINCE_SHORTNAME_MAP = Object.fromEntries(
  Object.entries(PROVINCE_FULLNAME_MAP).map(([shortName, fullName]) => [fullName, shortName])
);

function activeMode() {
  return (mapModeSelect?.value || "risk").toLowerCase();
}

function syncModeUI() {
  const mode = activeMode();
  if (mapModeRiskBtn) mapModeRiskBtn.classList.toggle("active", mode === "risk");
  if (mapModeHeatBtn) mapModeHeatBtn.classList.toggle("active", mode === "heat");
  if (mapModeHint) {
    mapModeHint.textContent =
      mode === "heat"
        ? "当前显示：热度地图（颜色越深说明传播热度越高）"
        : "当前显示：风险地图（红色区域风险更高）";
  }
}

function metricLabel(mode) {
  return mode === "heat" ? "热度" : "风险";
}

function metricValue(row, mode) {
  if (mode === "heat") return Number(row.heat_value ?? row.value ?? 0);
  return Number(row.risk_value ?? row.value ?? 0);
}

function normalizeProvinceName(rawName) {
  const txt = String(rawName || "").trim();
  if (!txt) return "";
  if (PROVINCE_SHORTNAME_MAP[txt]) return PROVINCE_SHORTNAME_MAP[txt];
  if (PROVINCE_FULLNAME_MAP[txt]) return txt;
  return txt
    .replace("特别行政区", "")
    .replace("维吾尔自治区", "")
    .replace("回族自治区", "")
    .replace("壮族自治区", "")
    .replace("自治区", "")
    .replace("省", "")
    .replace("市", "");
}

function currentTopicKeyword() {
  return (topicSelect?.value || topicInput?.value || "").trim();
}

function buildBaseQuery() {
  return (
    `start_date=${encodeURIComponent(startDateInput.value || "")}` +
    `&end_date=${encodeURIComponent(endDateInput.value || "")}` +
    `&platform=${encodeURIComponent(platformSelect.value || "")}` +
    `&theme=${encodeURIComponent((themeSelect?.value || "").trim())}` +
    `&sub_theme=${encodeURIComponent((subThemeSelect?.value || "").trim())}` +
    `&topic=${encodeURIComponent(currentTopicKeyword())}`
  );
}

async function ensureChinaMap() {
  if (chinaMapLoaded) return;
  const urls = [
    "https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json",
    "https://fastly.jsdelivr.net/npm/echarts@5/map/json/china.json",
  ];
  for (const url of urls) {
    try {
      const res = await fetch(url);
      if (!res.ok) continue;
      const mapJson = await res.json();
      echarts.registerMap("china", mapJson);
      chinaMapLoaded = true;
      return;
    } catch (_) {}
  }
  throw new Error("中国地图底图加载失败");
}

function renderSummary(summary) {
  const s = summary || {};
  totalEventsEl.textContent = Number(s.total_events || 0).toLocaleString();
  provinceCountEl.textContent = Number(s.province_count || 0);
  highRiskProvincesEl.textContent = Number(s.high_risk_provinces || 0);
  peakHeatProvinceEl.textContent = s.peak_heat_province || "-";
  peakRiskProvinceEl.textContent = s.peak_risk_province || "-";
}

function renderTrend7d(data) {
  const dates = (data?.dates || []).slice(-7);
  const risk = (data?.risk_index || []).slice(-7);
  const attack = (data?.attack_ratio || []).slice(-7);
  trendChart.setOption(
    {
      animationDuration: 260,
      tooltip: { trigger: "axis" },
      legend: {
        data: ["综合RI", "攻击占比(%)"],
        top: 8,
        textStyle: { color: "#c3d0f2" },
      },
      grid: { left: 42, right: 18, top: 42, bottom: 26 },
      xAxis: {
        type: "category",
        data: dates,
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
          name: "综合RI",
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 3, color: "#74a6ff" },
          areaStyle: { color: "rgba(116,166,255,0.15)" },
          data: risk,
        },
        {
          name: "攻击占比(%)",
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, type: "dashed", color: "#ff6b8a" },
          data: attack,
        },
      ],
    },
    true
  );
}

function renderRegionRanking(list, mode) {
  if (!list.length) {
    regionList.innerHTML = "<div>暂无地区数据</div>";
    regionTotalPages = 1;
    regionCurrentPage = 1;
    if (regionPageInfo) regionPageInfo.textContent = "第 1 / 1 页";
    return;
  }
  const sorted = [...list]
    .sort((a, b) => metricValue(b, mode) - metricValue(a, mode))
  const pageSize = 6;
  regionTotalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  regionCurrentPage = Math.min(regionCurrentPage, regionTotalPages);
  const start = (regionCurrentPage - 1) * pageSize;
  const pageItems = sorted.slice(start, start + pageSize);
  const label = metricLabel(mode);
  regionList.innerHTML = pageItems
    .map(
      (r, idx) => `
      <div class="rank-item">
        <div>#${start + idx + 1} ${r.name}<span class="rank-score">${metricValue(r, mode)}</span></div>
        <div>${label}值：${metricValue(r, mode)} | 事件数：${r.event_count || 0}</div>
        <div>攻击占比：${r.attack_ratio || 0}%</div>
      </div>
      `
    )
    .join("");
  if (regionPageInfo) regionPageInfo.textContent = `第 ${regionCurrentPage} / ${regionTotalPages} 页`;
  if (regionPrevPageBtn) regionPrevPageBtn.disabled = regionCurrentPage <= 1;
  if (regionNextPageBtn) regionNextPageBtn.disabled = regionCurrentPage >= regionTotalPages;
}

function renderProvinceDetail(payload, province) {
  const topTopics = payload?.top_topics || [];
  const events = payload?.recent_events || [];
  provinceDetailTitle.textContent = `省份详情 - ${province}`;
  if (!topTopics.length && !events.length) {
    provinceDetailList.innerHTML = "<div>该省暂无匹配数据</div>";
    return;
  }
  const topicRows = topTopics
    .map(
      (x, idx) => `
      <div class="rank-item">
        <div>#${idx + 1} ${x.topic_name}</div>
        <div>风险：${x.risk_index} | 热度：${x.heat_score} | 事件数：${x.event_count}</div>
      </div>
    `
    )
    .join("");
  const eventRows = events
    .slice(0, 3)
    .map(
      (x) => `
      <div class="rank-item">
        <div>${x.topic_name}</div>
        <div class="content-ellipsis">${x.content || ""}</div>
      </div>
    `
    )
    .join("");
  provinceDetailList.innerHTML = topicRows + eventRows;
}

function renderMap(list, mode) {
  const label = metricLabel(mode);
  const title = mode === "heat" ? "全国舆情热度分布" : "全国舆情风险分布";
  const colors =
    mode === "heat"
      ? ["#8bd3ff", "#67e8f9", "#fed784", "#ff8a65"]
      : ["#b3f4d8", "#fed784", "#ff6b8a"];
  const mapSeriesData = list.map((r) => ({
    ...r,
    name: PROVINCE_FULLNAME_MAP[r.name] || r.name,
    value: metricValue(r, mode),
  }));

  mapChart.setOption(
    {
      animationDuration: 320,
      animationEasing: "cubicOut",
      title: {
        text: title,
        left: "center",
        top: 8,
        textStyle: { color: "#e8eefc", fontSize: 15, fontWeight: 600 },
      },
      tooltip: {
        trigger: "item",
        formatter: (params) => {
          const d = params.data || {};
          return `${params.name}<br/>${label}值: ${d.value ?? 0}<br/>事件数: ${d.event_count ?? 0}<br/>攻击占比: ${d.attack_ratio ?? 0}%`;
        },
      },
      visualMap: {
        min: 0,
        max: 100,
        text: [`高${label}`, `低${label}`],
        calculable: true,
        inRange: { color: colors },
        textStyle: { color: "#dbe7ff" },
      },
      series: [
        {
          name: `${label}热力`,
          type: "map",
          map: "china",
          roam: true,
          emphasis: {
            itemStyle: { areaColor: "#7ea9ff" },
            label: { color: "#fff" },
          },
          itemStyle: {
            borderColor: "rgba(255,255,255,0.3)",
            borderWidth: 1,
          },
          data: mapSeriesData,
        },
      ],
    },
    true
  );
}

function renderHotTopics(list) {
  if (!list.length) {
    hotTopicList.innerHTML = "<div>暂无热榜数据</div>";
    return;
  }
  hotTopicList.innerHTML = list
    .slice(0, 10)
    .map(
      (x, idx) => `
      <div class="rank-item">
        <div>#${idx + 1} ${x.topic_name || "未分类"}</div>
        <div>热度：${Number(x.heat_score || 0).toLocaleString()} | 平台：${x.platform || "-"}</div>
      </div>
    `
    )
    .join("");
}

function repaintByMode() {
  const mode = activeMode();
  syncModeUI();
  renderMap(currentMapData, mode);
  renderRegionRanking(currentMapData, mode);
  renderSummary(currentSummary);
}

async function loadProvinceDetail(province) {
  if (!province) return;
  showSkeleton(provinceDetailList, 4);
  try {
    const data = await apiGet(`/mvp/api/province-detail?${buildBaseQuery()}&province=${encodeURIComponent(province)}`);
    renderProvinceDetail(data.data || {}, province);
  } catch (err) {
    provinceDetailTitle.textContent = `省份详情 - ${province}`;
    provinceDetailList.innerHTML = `<div>加载失败：${err.message}</div>`;
  }
}

async function refreshTopicSelectors(resetTopic = false) {
  const opts = await loadTopicOptions({
    platform: platformSelect.value,
    startDate: startDateInput.value,
    endDate: endDateInput.value,
    theme: (themeSelect?.value || "").trim(),
    subTheme: (subThemeSelect?.value || "").trim(),
  });
  fillSelectOptions(themeSelect, opts.themes || [], "全部一级主题");
  fillSelectOptions(subThemeSelect, opts.sub_themes || [], "全部次主题");
  fillSelectOptions(topicSelect, opts.topics || [], "可选话题（可不选）");
  if (resetTopic) {
    if (topicInput) topicInput.value = "";
  }
}

async function loadHeatmap() {
  showSkeleton(regionList, 6);
  showSkeleton(hotTopicList, 4);
  showSkeleton(provinceDetailList, 4);
  try {
    await ensureChinaMap();
    const baseQuery = buildBaseQuery();
    const [mapResp, rankingResp, trendResp] = await Promise.all([
      apiGet(`/mvp/api/heatmap-china?${baseQuery}`),
      apiGet(`/mvp/api/ranking?${baseQuery}&top_n=10`),
      apiGet(`/mvp/api/trend-30d?${baseQuery}`),
    ]);
    currentMapData = mapResp.data || [];
    currentSummary = mapResp.meta?.summary || null;
    regionCurrentPage = 1;
    repaintByMode();
    renderHotTopics(rankingResp.data || []);
    renderTrend7d(trendResp.data || {});
    if (selectedProvince) {
      await loadProvinceDetail(selectedProvince);
    } else {
      provinceDetailTitle.textContent = "省份详情（点击地图省份）";
      provinceDetailList.innerHTML = "<div>点击地图中的任一省份，可查看该省高风险主题与典型事件。</div>";
    }
  } catch (err) {
    regionList.innerHTML = `<div>加载失败：${err.message}</div>`;
    hotTopicList.innerHTML = `<div>加载失败：${err.message}</div>`;
    provinceDetailList.innerHTML = `<div>加载失败：${err.message}</div>`;
    mapChart.setOption(
      {
        title: {
          text: `地图加载失败: ${err.message}`,
          left: "center",
          top: "center",
          textStyle: { color: "#fff", fontSize: 14 },
        },
      },
      true
    );
  }
}

mapChart.on("click", (params) => {
  const province = normalizeProvinceName(params?.name || "");
  selectedProvince = province;
  loadProvinceDetail(province);
});

window.addEventListener("resize", () => {
  mapChart.resize();
  trendChart.resize();
});
loadHeatmapBtn.addEventListener("click", loadHeatmap);
platformSelect.addEventListener("change", async () => {
  await refreshTopicSelectors(true);
  loadHeatmap();
});
mapModeSelect?.addEventListener("change", repaintByMode);
mapModeRiskBtn?.addEventListener("click", () => {
  if (mapModeSelect) mapModeSelect.value = "risk";
  repaintByMode();
});
mapModeHeatBtn?.addEventListener("click", () => {
  if (mapModeSelect) mapModeSelect.value = "heat";
  repaintByMode();
});
themeSelect?.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
  loadHeatmap();
});
subThemeSelect?.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
  loadHeatmap();
});
topicSelect?.addEventListener("change", () => {
  if (topicSelect.value && topicInput) topicInput.value = topicSelect.value;
});
startDateInput.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});
endDateInput.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});
regionPrevPageBtn?.addEventListener("click", () => {
  if (regionCurrentPage > 1) {
    regionCurrentPage -= 1;
    renderRegionRanking(currentMapData, activeMode());
  }
});
regionNextPageBtn?.addEventListener("click", () => {
  if (regionCurrentPage < regionTotalPages) {
    regionCurrentPage += 1;
    renderRegionRanking(currentMapData, activeMode());
  }
});

formatDateInputDefaults(startDateInput, endDateInput, 30);
syncModeUI();
refreshTopicSelectors(true).then(loadHeatmap);
