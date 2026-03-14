const platformSelect = document.getElementById("platformSelect");
const themeSelect = document.getElementById("themeSelect");
const subThemeSelect = document.getElementById("subThemeSelect");
const topicSelect = document.getElementById("topicSelect");
const topicInput = document.getElementById("topicInput");
const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");
const loadEventChainBtn = document.getElementById("loadEventChainBtn");
const eventMetricCards = document.getElementById("eventMetricCards");
const eventCommentsBody = document.getElementById("eventCommentsBody");
const chainChart = echarts.init(document.getElementById("chainChart"));

function eventChainUrl() {
  const topicName = (topicSelect?.value || topicInput.value).trim();
  return `/mvp/api/event-chain?platform=${platformSelect.value}&topic_name=${encodeURIComponent(
    topicName
  )}&start_date=${startDateInput.value}&end_date=${endDateInput.value}&theme=${encodeURIComponent(
    (themeSelect?.value || "").trim()
  )}&sub_theme=${encodeURIComponent((subThemeSelect?.value || "").trim())}`;
}

function renderMetricCards(data) {
  const cards = [
    { label: "Topic RI", value: data.topic_ri },
    { label: "加权RI", value: data.weighted_ri },
    { label: "平均RI", value: data.avg_ri },
    { label: "攻击占比", value: `${(data.attack_ratio * 100).toFixed(2)}%` },
    { label: "危险占比", value: `${(data.danger_ratio * 100).toFixed(2)}%` },
    { label: "语境风险占比", value: `${((data.context_ratio || 0) * 100).toFixed(2)}%` },
    { label: "建议", value: data.suggestion },
  ];
  const cardHtml = cards
    .map(
      (c) => `<div class="rank-item">
      <div><strong>${c.label}</strong></div>
      <div style="margin-top:6px;line-height:1.45">${c.value}</div>
    </div>`
    )
    .join("");
  const candidateHtml = (data.candidate_topics || [])
    .slice(0, 6)
    .map(
      (x, idx) => `
      <div class="rank-item">
        <div>#${idx + 1} ${x.topic_name || "未分类"}</div>
        <div>RI: ${x.topic_ri} | 评论数: ${x.comment_count || 0}</div>
      </div>
    `
    )
    .join("");
  eventMetricCards.innerHTML = cardHtml + (candidateHtml ? `<div class="rank-item"><div><strong>高风险候选话题</strong></div></div>${candidateHtml}` : "");
}

function renderComments(items) {
  if (!items.length) {
    eventCommentsBody.innerHTML = '<tr><td colspan="7">暂无评论样本</td></tr>';
    return;
  }
  eventCommentsBody.innerHTML = items
    .map(
      (x) => `<tr>
    <td>${x.comment_id || "-"}</td>
    <td>${x.like_count || 0}</td>
    <td><span class="risk-badge ${x.risk_index >= 80 ? "risk-high" : x.risk_index >= 50 ? "risk-mid" : "risk-low"}">${x.risk_index}</span></td>
    <td>${x.sentiment_score || "-"}</td>
    <td>${x.impact_coefficient || "-"}</td>
    <td>${x.risk_reason || "-"}</td>
    <td class="content-ellipsis" title="${(x.text || "").replace(/"/g, "&quot;")}">${x.text || "-"}</td>
  </tr>`
    )
    .join("");
}

function renderChainChart(data) {
  const nodes = [
    { name: "原始评论", value: data.comment_count || 0, x: 120, y: 100 },
    { name: "情感分析", value: data.avg_ri || 0, x: 320, y: 100 },
    { name: "攻击占比", value: ((data.attack_ratio || 0) * 100).toFixed(2), x: 520, y: 100 },
    { name: "话题RI", value: data.topic_ri || 0, x: 720, y: 100 },
    { name: "响应建议", value: data.suggestion || "", x: 920, y: 100 },
  ];
  const links = [
    { source: "原始评论", target: "情感分析" },
    { source: "情感分析", target: "攻击占比" },
    { source: "攻击占比", target: "话题RI" },
    { source: "话题RI", target: "响应建议" },
  ];
  chainChart.setOption(
    {
      animationDuration: 320,
      tooltip: {
        formatter: (p) => (p.dataType === "node" ? `${p.data.name}<br/>${p.data.value}` : `${p.data.source} -> ${p.data.target}`),
      },
      series: [
        {
          type: "graph",
          layout: "none",
          roam: true,
          symbolSize: 72,
          label: {
            show: true,
            color: "#ffffff",
            fontSize: 12,
            lineHeight: 16,
            backgroundColor: "rgba(8, 16, 40, 0.68)",
            borderRadius: 6,
            padding: [4, 8],
          },
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: 8,
          lineStyle: { color: "rgba(116,166,255,0.92)", width: 2.8 },
          itemStyle: { color: "#1f4fd6", borderColor: "#98b6ff", borderWidth: 2 },
          data: nodes,
          links,
        },
      ],
    },
    true
  );
}

async function loadEventChain() {
  const finalTopic = (topicSelect?.value || topicInput.value || "").trim();
  eventMetricCards.innerHTML = '<div class="skeleton"></div>';
  eventCommentsBody.innerHTML = '<tr><td colspan="7"><div class="skeleton"></div></td></tr>';
  try {
    const res = await apiGet(eventChainUrl());
    const data = res.data || {};
    renderMetricCards(data);
    renderComments(data.top_comments || []);
    renderChainChart(data);
  } catch (err) {
    eventMetricCards.innerHTML = `<div>加载失败：${err.message}</div>`;
    eventCommentsBody.innerHTML = `<tr><td colspan="7">加载失败：${err.message}</td></tr>`;
    chainChart.setOption({ title: { text: `加载失败: ${err.message}`, left: "center", textStyle: { color: "#fff" } } }, true);
  }
}

window.addEventListener("resize", () => chainChart.resize());
loadEventChainBtn.addEventListener("click", loadEventChain);
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
});
themeSelect?.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});
subThemeSelect?.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});
startDateInput.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});
endDateInput.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});
formatDateInputDefaults(startDateInput, endDateInput, 30);
refreshTopicSelectors(true);
