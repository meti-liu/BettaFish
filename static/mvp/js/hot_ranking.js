const topicInput = document.getElementById("topicInput");
const platformSelect = document.getElementById("platformSelect");
const themeSelect = document.getElementById("themeSelect");
const subThemeSelect = document.getElementById("subThemeSelect");
const topicSelect = document.getElementById("topicSelect");
const startDateInput = document.getElementById("startDate");
const endDateInput = document.getElementById("endDate");
const searchBtn = document.getElementById("searchBtn");
const eventsBody = document.getElementById("eventsBody");
const rankingList = document.getElementById("rankingList");
const prevPage = document.getElementById("prevPage");
const nextPage = document.getElementById("nextPage");
const pageInfo = document.getElementById("pageInfo");
const wordcloudChart = echarts.init(document.getElementById("wordcloudChart"));
const platformChart = echarts.init(document.getElementById("platformChart"));
const commentsBody = document.getElementById("commentsBody");
const topicCommentsMeta = document.getElementById("topicCommentsMeta");

let currentPage = 1;
let totalPages = 1;
let selectedTopic = "";

function riskClass(ri) {
  if (ri >= 80) return "risk-high";
  if (ri >= 50) return "risk-mid";
  return "risk-low";
}

function currentFilters() {
  const pickedTopic = (topicSelect?.value || "").trim();
  const typedTopic = topicInput.value.trim();
  return {
    platform: platformSelect.value,
    theme: encodeURIComponent((themeSelect?.value || "").trim()),
    subTheme: encodeURIComponent((subThemeSelect?.value || "").trim()),
    topic: encodeURIComponent(pickedTopic || typedTopic),
    startDate: startDateInput.value,
    endDate: endDateInput.value,
  };
}

function renderEvents(items) {
  if (!items.length) {
    eventsBody.innerHTML = '<tr><td colspan="5">暂无数据</td></tr>';
    return;
  }
  eventsBody.innerHTML = items
    .map((item) => {
      const content = (item.content || "").replace(/\s+/g, " ").trim();
      return `
      <tr>
        <td>${item.create_time || "-"}</td>
        <td><a href="#" class="topic-link" data-topic="${(item.topic_name || "-").replace(/"/g, "&quot;")}">${item.topic_name || "-"}</a></td>
        <td class="content-ellipsis" title="${content}">${content || "-"}</td>
        <td>${item.liked_count}/${item.comments_count}/${item.shared_count}</td>
        <td><span class="risk-badge ${riskClass(item.risk_index)}">${item.risk_index}</span></td>
      </tr>`;
    })
    .join("");
}

function renderRanking(items) {
  if (!items.length) {
    rankingList.innerHTML = "<div>暂无排行数据</div>";
    return;
  }
  rankingList.innerHTML = items
    .map(
      (item, idx) => `
      <div class="rank-item">
        <div>#${idx + 1} ${item.topic_name || "未分类"} <span class="rank-score">${item.heat_score}</span></div>
        <div>${item.nickname || "匿名用户"} · ${item.create_time || "-"}</div>
      </div>
    `
    )
    .join("");
}

async function loadEvents() {
  const f = currentFilters();
  try {
    eventsBody.innerHTML = '<tr><td colspan="5"><div class="skeleton"></div></td></tr>';
    const data = await apiGet(
      `/mvp/api/hot-events?page=${currentPage}&page_size=10&topic=${f.topic}&start_date=${f.startDate}&end_date=${f.endDate}&platform=${f.platform}`
      + `&theme=${f.theme}&sub_theme=${f.subTheme}`
    );
    renderEvents(data.data || []);
    totalPages = data.pagination.total_pages || 1;
    pageInfo.textContent = `第 ${currentPage} / ${totalPages} 页`;
  } catch (err) {
    eventsBody.innerHTML = `<tr><td colspan="5">加载失败：${err.message}</td></tr>`;
  }
}

async function loadRanking() {
  const f = currentFilters();
  showSkeleton(rankingList, 5);
  try {
    const data = await apiGet(
      `/mvp/api/ranking?top_n=10&topic=${f.topic}&start_date=${f.startDate}&end_date=${f.endDate}&platform=${f.platform}`
      + `&theme=${f.theme}&sub_theme=${f.subTheme}`
    );
    renderRanking(data.data || []);
  } catch (err) {
    rankingList.innerHTML = `<div>加载失败：${err.message}</div>`;
  }
}

async function loadWordcloud() {
  const f = currentFilters();
  const data = await apiGet(
    `/mvp/api/wordcloud?topic=${f.topic}&start_date=${f.startDate}&end_date=${f.endDate}&platform=${f.platform}&top_n=80&theme=${f.theme}&sub_theme=${f.subTheme}`
  );
  wordcloudChart.setOption(
    {
      animationDuration: 300,
      tooltip: { trigger: "item" },
      series: [
        {
          type: "wordCloud",
          shape: "circle",
          gridSize: 10,
          sizeRange: [12, 48],
          rotationRange: [-45, 90],
          textStyle: {
            color: () => {
              const colors = ["#74a6ff", "#67e8f9", "#52d89c", "#ff6b8a", "#fed784"];
              return colors[Math.floor(Math.random() * colors.length)];
            },
          },
          emphasis: {
            textStyle: {
              shadowBlur: 8,
              shadowColor: "#333",
            },
          },
          data: data.data || [],
        },
      ],
    },
    true
  );
}

async function loadPlatformDistribution() {
  const f = currentFilters();
  const data = await apiGet(
    `/mvp/api/platform-distribution?topic=${f.topic}&start_date=${f.startDate}&end_date=${f.endDate}&theme=${f.theme}&sub_theme=${f.subTheme}`
  );
  const pieData = data.data || [];
  platformChart.setOption(
    {
      animationDuration: 280,
      tooltip: { trigger: "item" },
      legend: { bottom: 0, textStyle: { color: "#c3d0f2" } },
      series: [
        {
          type: "pie",
          radius: ["40%", "70%"],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 8, borderColor: "rgba(0,0,0,0.2)", borderWidth: 1 },
          label: { color: "#e8eefc" },
          data: pieData,
        },
      ],
    },
    true
  );
}

function renderComments(items) {
  if (!items.length) {
    commentsBody.innerHTML = '<tr><td colspan="4">暂无评论数据</td></tr>';
    return;
  }
  commentsBody.innerHTML = items
    .map((it) => {
      const content = (it.content || "").replace(/\s+/g, " ").trim();
      return `
      <tr>
        <td>${it.create_time || "-"}</td>
        <td>${it.nickname || "匿名"}</td>
        <td class="content-ellipsis" title="${content}">${content || "-"}</td>
        <td>${it.like_count || 0}</td>
      </tr>`;
    })
    .join("");
}

async function loadTopicComments(topicName) {
  selectedTopic = topicName || "";
  if (!selectedTopic || selectedTopic === "-") {
    topicCommentsMeta.textContent = "未选择话题";
    commentsBody.innerHTML = '<tr><td colspan="4">请先点击上方热点话题</td></tr>';
    return;
  }
  const f = currentFilters();
  topicCommentsMeta.textContent = `${f.platform} · ${selectedTopic}`;
  commentsBody.innerHTML = '<tr><td colspan="4"><div class="skeleton"></div></td></tr>';
  try {
    const data = await apiGet(
      `/mvp/api/topic-comments?platform=${f.platform}&topic_name=${encodeURIComponent(
        selectedTopic
      )}&start_date=${f.startDate}&end_date=${f.endDate}&page=1&page_size=20&theme=${f.theme}&sub_theme=${f.subTheme}`
    );
    renderComments(data.data || []);
  } catch (err) {
    commentsBody.innerHTML = `<tr><td colspan="4">加载失败：${err.message}</td></tr>`;
  }
}

async function loadAll() {
  await Promise.all([loadEvents(), loadRanking(), loadWordcloud(), loadPlatformDistribution()]);
  if (selectedTopic) {
    await loadTopicComments(selectedTopic);
  }
}

searchBtn.addEventListener("click", () => {
  currentPage = 1;
  loadAll();
});

prevPage.addEventListener("click", () => {
  if (currentPage > 1) {
    currentPage -= 1;
    loadEvents();
  }
});

nextPage.addEventListener("click", () => {
  if (currentPage < totalPages) {
    currentPage += 1;
    loadEvents();
  }
});

eventsBody.addEventListener("click", (e) => {
  const link = e.target.closest(".topic-link");
  if (!link) return;
  e.preventDefault();
  const topic = link.getAttribute("data-topic") || "";
  loadTopicComments(topic);
});

platformSelect.addEventListener("change", () => {
  currentPage = 1;
  selectedTopic = "";
  topicCommentsMeta.textContent = "未选择话题";
  commentsBody.innerHTML = '<tr><td colspan="4">请先点击上方热点话题</td></tr>';
  loadAll();
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
  if (resetDependent) {
    topicInput.value = "";
  }
}

themeSelect?.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
  currentPage = 1;
  loadAll();
});

subThemeSelect?.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
  currentPage = 1;
  loadAll();
});

topicSelect?.addEventListener("change", () => {
  if (topicSelect.value) topicInput.value = topicSelect.value;
});

startDateInput.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});
endDateInput.addEventListener("change", async () => {
  await refreshTopicSelectors(false);
});

window.addEventListener("resize", () => {
  wordcloudChart.resize();
  platformChart.resize();
});

formatDateInputDefaults(startDateInput, endDateInput, 30);
refreshTopicSelectors(true).then(loadAll);
