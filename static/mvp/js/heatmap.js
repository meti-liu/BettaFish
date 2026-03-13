const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");
const platformSelect = document.getElementById("platformSelect");
const loadHeatmapBtn = document.getElementById("loadHeatmapBtn");
const regionList = document.getElementById("regionList");
const mapChart = echarts.init(document.getElementById("chinaMap"));

let chinaMapLoaded = false;
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

function renderRegionRanking(list) {
  if (!list.length) {
    regionList.innerHTML = "<div>暂无地区数据</div>";
    return;
  }
  const sorted = [...list].sort((a, b) => b.value - a.value).slice(0, 12);
  regionList.innerHTML = sorted
    .map(
      (r, idx) => `
      <div class="rank-item">
        <div>#${idx + 1} ${r.name}<span class="rank-score">${r.value}</span></div>
        <div>事件数：${r.event_count || 0}</div>
      </div>
      `
    )
    .join("");
}

async function loadHeatmap() {
  showSkeleton(regionList, 6);
  try {
    await ensureChinaMap();
    const data = await apiGet(
      `/mvp/api/heatmap-china?start_date=${startDateInput.value}&end_date=${endDateInput.value}&platform=${platformSelect.value}`
    );

    const mapData = data.data || [];
    renderRegionRanking(mapData);
    const mapSeriesData = mapData.map((r) => ({
      ...r,
      name: PROVINCE_FULLNAME_MAP[r.name] || r.name,
    }));

    mapChart.setOption(
      {
        animationDuration: 320,
        animationEasing: "cubicOut",
        tooltip: {
          trigger: "item",
          formatter: (params) => `${params.name}<br/>RI: ${params.data?.value ?? 0}`,
        },
        visualMap: {
          min: 0,
          max: 100,
          text: ["高风险", "低风险"],
          calculable: true,
          inRange: {
            color: ["#b3f4d8", "#fed784", "#ff6b8a"],
          },
          textStyle: { color: "#dbe7ff" },
        },
        series: [
          {
            name: "风险热力",
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
  } catch (err) {
    regionList.innerHTML = `<div>加载失败：${err.message}</div>`;
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

window.addEventListener("resize", () => mapChart.resize());
loadHeatmapBtn.addEventListener("click", loadHeatmap);
platformSelect.addEventListener("change", loadHeatmap);

formatDateInputDefaults(startDateInput, endDateInput, 30);
loadHeatmap();
