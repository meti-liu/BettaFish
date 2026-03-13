const topicInput = document.getElementById("topicInput");
const platformSelect = document.getElementById("platformSelect");
const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");
const loadTrendBtn = document.getElementById("loadTrendBtn");

const riskChart = echarts.init(document.getElementById("riskChart"));
const countChart = echarts.init(document.getElementById("countChart"));
const riskMatrixChart = echarts.init(document.getElementById("riskMatrixChart"));
const riskLevelChart = echarts.init(document.getElementById("riskLevelChart"));
const topRiskTopicChart = echarts.init(document.getElementById("topRiskTopicChart"));

function requestUrl() {
  const topic = encodeURIComponent(topicInput.value.trim());
  return `/mvp/api/trend-30d?topic=${topic}&start_date=${startDateInput.value}&end_date=${endDateInput.value}&platform=${platformSelect.value}`;
}

function setChart(chart, title, dates, values, color) {
  chart.setOption(
    {
      animationDuration: 300,
      animationEasing: "cubicOut",
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: dates,
        axisLabel: { color: "#c3d0f2" },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#c3d0f2" },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
      },
      series: [
        {
          name: title,
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 3, color },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: `${color}80` },
              { offset: 1, color: `${color}10` },
            ]),
          },
          data: values,
        },
      ],
    },
    true
  );
}

async function loadTrend() {
  const baseTitle = { left: "center", textStyle: { color: "#fff" } };
  try {
    const trendUrl = requestUrl();
    const topic = encodeURIComponent(topicInput.value.trim());
    const matrixUrl = `/mvp/api/risk-matrix?topic=${topic}&start_date=${startDateInput.value}&end_date=${endDateInput.value}&platform=${platformSelect.value}&max_topics=120`;
    const [trendData, matrixData] = await Promise.all([apiGet(trendUrl), apiGet(matrixUrl)]);

    const dates = trendData.data.dates || [];
    setChart(riskChart, "RI", dates, trendData.data.risk_index || [], "#74a6ff");
    setChart(countChart, "话题数", dates, trendData.data.topic_counts || [], "#67e8f9");

    const bubbles = matrixData.data?.bubbles || [];
    riskMatrixChart.setOption(
      {
        animationDuration: 300,
        tooltip: {
          trigger: "item",
          formatter: (p) => {
            const d = p.data.raw;
            return `${d.topic_name}<br/>RI: ${d.ri_score}<br/>速度分: ${d.velocity_score}<br/>恶意度: ${d.malicious_score}<br/>帖子数: ${d.note_count}`;
          },
        },
        xAxis: {
          type: "value",
          name: "传播速度分",
          min: 0,
          max: 100,
          axisLabel: { color: "#c3d0f2" },
          splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
        },
        yAxis: {
          type: "value",
          name: "恶意度分",
          min: 0,
          max: 100,
          axisLabel: { color: "#c3d0f2" },
          splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
        },
        visualMap: {
          min: 0,
          max: 100,
          dimension: 3,
          orient: "horizontal",
          left: "center",
          bottom: 4,
          text: ["高RI", "低RI"],
          textStyle: { color: "#c3d0f2" },
          inRange: { color: ["#52d89c", "#fed784", "#ff6b8a"] },
        },
        series: [
          {
            type: "scatter",
            symbolSize: (v) => Math.max(8, Math.min(45, Math.sqrt(v[2]) * 2.5)),
            data: bubbles.map((b) => ({
              value: [b.velocity_score, b.malicious_score, b.note_count, b.ri_score],
              raw: b,
            })),
          },
        ],
      },
      true
    );

    const riskDist = matrixData.data?.risk_distribution || [];
    riskLevelChart.setOption(
      {
        animationDuration: 280,
        tooltip: { trigger: "item" },
        legend: { bottom: 0, textStyle: { color: "#c3d0f2" } },
        series: [
          {
            type: "pie",
            radius: ["40%", "72%"],
            label: { color: "#e8eefc" },
            data: riskDist,
          },
        ],
      },
      true
    );

    const topRisk = matrixData.data?.top_risky_topics || [];
    topRiskTopicChart.setOption(
      {
        animationDuration: 320,
        tooltip: { trigger: "axis" },
        grid: { left: 160, right: 32, top: 24, bottom: 30 },
        xAxis: {
          type: "value",
          axisLabel: { color: "#c3d0f2" },
          splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
        },
        yAxis: {
          type: "category",
          axisLabel: { color: "#c3d0f2", width: 140, overflow: "truncate" },
          data: topRisk.map((x) => x.topic_name).reverse(),
        },
        series: [
          {
            type: "bar",
            data: topRisk.map((x) => x.ri_score).reverse(),
            itemStyle: { color: "#ff6b8a" },
            label: { show: true, position: "right", color: "#e8eefc" },
          },
        ],
      },
      true
    );
  } catch (err) {
    riskChart.setOption({ title: { ...baseTitle, text: `加载失败: ${err.message}` } });
    countChart.setOption({ title: { ...baseTitle, text: `加载失败: ${err.message}` } });
    riskMatrixChart.setOption({ title: { ...baseTitle, text: `加载失败: ${err.message}` } });
    riskLevelChart.setOption({ title: { ...baseTitle, text: `加载失败: ${err.message}` } });
    topRiskTopicChart.setOption({ title: { ...baseTitle, text: `加载失败: ${err.message}` } });
  }
}

window.addEventListener("resize", () => {
  riskChart.resize();
  countChart.resize();
  riskMatrixChart.resize();
  riskLevelChart.resize();
  topRiskTopicChart.resize();
});

loadTrendBtn.addEventListener("click", loadTrend);
platformSelect.addEventListener("change", loadTrend);
formatDateInputDefaults(startDateInput, endDateInput, 30);
loadTrend();
