const form = document.querySelector("#handle-form");
const input = document.querySelector("#handle-input");
const refreshButton = document.querySelector("#refresh-button");
const statusStrip = document.querySelector("#status-strip");
const metricsGrid = document.querySelector("#metrics-grid");
const evaluationGrid = document.querySelector("#evaluation-grid");
const growthGrid = document.querySelector("#growth-grid");
const recommendationGrid = document.querySelector("#recommendation-grid");
const planGrid = document.querySelector("#plan-grid");
const topicTable = document.querySelector("#topic-table");
const priorityFilters = document.querySelector("#priority-filters");

let currentHandle = "";
let currentData = null;
let activePriority = "All";
const charts = {};

const chartColors = {
  blue: "#3563e9",
  green: "#168a5c",
  red: "#c44d58",
  amber: "#b77717",
  violet: "#7446a8",
  gray: "#667085",
};

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const handle = input.value.trim();
  if (handle) analyze(handle, false);
});

refreshButton.addEventListener("click", () => {
  if (currentHandle) analyze(currentHandle, true);
});

window.addEventListener("load", () => {
  const params = new URLSearchParams(window.location.search);
  const handle = params.get("handle") || localStorage.getItem("lastHandle") || "";
  if (handle) {
    input.value = handle;
    analyze(handle, false);
  } else {
    renderEmptyState();
  }
  lucide.createIcons();
});

async function analyze(handle, forceRefresh) {
  currentHandle = handle;
  localStorage.setItem("lastHandle", handle);
  setLoading(handle, forceRefresh);
  try {
    const response = await fetch(
      `/api/analyze/${encodeURIComponent(handle)}?limit=10000&force_refresh=${forceRefresh ? "true" : "false"}`
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Request failed with ${response.status}`);
    }
    currentData = await response.json();
    activePriority = "All";
    renderDashboard(currentData);
  } catch (error) {
    renderError(error);
  } finally {
    lucide.createIcons();
  }
}

function setLoading(handle, forceRefresh) {
  statusStrip.classList.add("loading");
  refreshButton.disabled = true;
  statusStrip.querySelector(".eyebrow").textContent = forceRefresh ? "Refreshing" : "Analyzing";
  statusStrip.querySelector("strong").textContent = `Building profile for ${handle}`;
}

function renderDashboard(data) {
  statusStrip.classList.remove("loading");
  refreshButton.disabled = false;
  statusStrip.querySelector(".eyebrow").textContent = data.source;
  statusStrip.querySelector("strong").textContent =
    `${data.user.handle} - ${formatRank(data.user.rank)} - ${data.cache.submissions_loaded.toLocaleString()} submissions loaded`;

  renderMetrics(data);
  renderEvaluation(data.evaluation);
  renderGrowthBacktest(data.growth_backtest);
  renderCharts(data);
  renderFilters(data.recommendations);
  renderRecommendations(data.recommendations);
  renderPlan(data.plan);
  renderTopicTable(data.topic_stats);
}

function renderMetrics(data) {
  const profile = data.profile;
  const model = data.recommender_model || {};
  const metrics = [
    ["Rating", profile.inferred_rating, data.user.max_rating ? `max ${data.user.max_rating}` : "inferred"],
    ["Solved", profile.solved_count, `${profile.attempted_count} attempted`],
    ["Best solve", profile.best_solved_rating || "-", "highest rated AC"],
    ["Avg solve", profile.avg_solved_rating || "-", "accepted rating"],
    ["Weak tags", profile.weak_tags.length, profile.weak_tags.slice(0, 2).join(", ") || "none"],
    ["Recommender", "Stage 2", model.method || "content-based"],
    ["Streak", profile.max_streak_days, `${profile.active_days} active days`],
  ];

  metricsGrid.innerHTML = metrics
    .map(
      ([label, value, hint]) => `
        <article class="metric-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(String(value))}</strong>
          <small>${escapeHtml(String(hint))}</small>
        </article>
      `
    )
    .join("");
}

function renderEvaluation(evaluation) {
  if (!evaluation || evaluation.status !== "ok") {
    evaluationGrid.innerHTML = `
      <div class="empty-state">
        ${escapeHtml(evaluation?.message || "Not enough solved history to run temporal backtesting.")}
      </div>
    `;
    return;
  }
  const metrics = [
    [`Precision@${evaluation.k}`, percent(evaluation.precision_at_k), `${evaluation.hits.length}/${evaluation.k} held-out hits`],
    [`HitRate@${evaluation.k}`, percent(evaluation.hit_rate_at_k), "at least one future solve"],
    [`NDCG@${evaluation.k}`, percent(evaluation.ndcg_at_k), "ranking quality"],
    ["MRR", decimal(evaluation.mrr), "first useful rank"],
    ["Train solves", evaluation.train_solved, `before ${evaluation.cutoff_date}`],
    ["Holdout solves", evaluation.holdout_solved, "future solved set"],
  ];
  evaluationGrid.innerHTML = metrics
    .map(
      ([label, value, hint]) => `
        <article class="metric-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(String(value))}</strong>
          <small>${escapeHtml(String(hint))}</small>
        </article>
      `
    )
    .join("");
}

function renderGrowthBacktest(growth) {
  if (!growth || growth.status !== "ok") {
    growthGrid.innerHTML = `
      <div class="empty-state">
        ${escapeHtml(growth?.message || "Not enough rating history to estimate growth outcomes.")}
      </div>
    `;
    return;
  }
  const metrics = [
    ["Windows", growth.windows_evaluated, `${growth.window_days}-day lookahead`],
    ["Followed", growth.followed_windows, "high-adherence windows"],
    ["Delta if followed", signedNumber(growth.avg_rating_delta_followed), "avg rating change"],
    ["Delta baseline", signedNumber(growth.avg_rating_delta_baseline), "low-adherence windows"],
    ["Est. uplift", signedNumber(growth.estimated_rating_uplift), "followed minus baseline"],
    ["Skill gain", signedNumber(growth.avg_weak_tag_skill_gain), "weak-tag avg rating"],
  ];
  growthGrid.innerHTML = metrics
    .map(
      ([label, value, hint]) => `
        <article class="metric-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(String(value))}</strong>
          <small>${escapeHtml(String(hint))}</small>
        </article>
      `
    )
    .join("");
}

function renderCharts(data) {
  drawWeaknessChart(data.topic_stats.slice(0, 10));
  drawRatingChart(data.rating_history);
  drawTimelineChart(data.timeline);
  drawLanguageChart(data.languages.slice(0, 6));
}

function drawWeaknessChart(stats) {
  replaceChart("weakness", "weakness-chart", {
    type: "bar",
    data: {
      labels: stats.map((item) => item.tag),
      datasets: [
        {
          label: "Weakness",
          data: stats.map((item) => Math.round(item.weakness_score * 100)),
          backgroundColor: stats.map((item) => levelColor(item.level)),
          borderRadius: 6,
        },
      ],
    },
    options: baseChartOptions({
      indexAxis: "y",
      scales: {
        x: { min: 0, max: 100, grid: { color: "#eef1f4" } },
        y: { grid: { display: false } },
      },
    }),
  });
}

function drawRatingChart(history) {
  replaceChart("rating", "rating-chart", {
    type: "line",
    data: {
      labels: history.map((item) => shortContest(item.contest_name)),
      datasets: [
        {
          label: "Rating",
          data: history.map((item) => item.new_rating),
          borderColor: chartColors.blue,
          backgroundColor: "rgba(53, 99, 233, 0.12)",
          fill: true,
          tension: 0.32,
          pointRadius: 2,
        },
      ],
    },
    options: baseChartOptions({
      scales: {
        x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { display: false } },
        y: { grid: { color: "#eef1f4" } },
      },
    }),
  });
}

function drawTimelineChart(timeline) {
  replaceChart("timeline", "timeline-chart", {
    type: "bar",
    data: {
      labels: timeline.map((item) => item.month),
      datasets: [
        {
          label: "Accepted",
          data: timeline.map((item) => item.accepted),
          backgroundColor: chartColors.green,
          borderRadius: 5,
        },
        {
          label: "Rejected",
          data: timeline.map((item) => item.rejected),
          backgroundColor: chartColors.red,
          borderRadius: 5,
        },
      ],
    },
    options: baseChartOptions({
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, grid: { color: "#eef1f4" } },
      },
    }),
  });
}

function drawLanguageChart(languages) {
  replaceChart("language", "language-chart", {
    type: "doughnut",
    data: {
      labels: languages.map((item) => compactLanguage(item.language)),
      datasets: [
        {
          data: languages.map((item) => item.accepted),
          backgroundColor: [chartColors.blue, chartColors.green, chartColors.amber, chartColors.violet, chartColors.red, "#506070"],
          borderWidth: 0,
        },
      ],
    },
    options: baseChartOptions({
      cutout: "62%",
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, color: chartColors.gray } },
      },
    }),
  });
}

function replaceChart(key, elementId, config) {
  if (charts[key]) charts[key].destroy();
  const canvas = document.querySelector(`#${elementId}`);
  charts[key] = new Chart(canvas, config);
}

function baseChartOptions(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: true, labels: { color: chartColors.gray, boxWidth: 12 } },
      tooltip: { intersect: false, mode: "index" },
      ...(extra.plugins || {}),
    },
    ...extra,
  };
}

function renderFilters(recommendations) {
  const priorities = ["All", ...Array.from(new Set(recommendations.map((item) => item.priority)))];
  priorityFilters.innerHTML = priorities
    .map(
      (priority) => `
        <button class="pill ${priority === activePriority ? "active" : ""}" type="button" data-priority="${escapeHtml(priority)}">
          ${escapeHtml(priority)}
        </button>
      `
    )
    .join("");
  priorityFilters.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activePriority = button.dataset.priority;
      renderFilters(currentData.recommendations);
      renderRecommendations(currentData.recommendations);
    });
  });
}

function renderRecommendations(recommendations) {
  const visible =
    activePriority === "All" ? recommendations : recommendations.filter((item) => item.priority === activePriority);
  recommendationGrid.innerHTML =
    visible
      .map(
        (item) => `
          <article class="problem-card">
            <div class="problem-topline">
              <span class="badge ${escapeHtml(item.priority)}">${escapeHtml(item.priority)}</span>
              <strong>${item.rating}</strong>
            </div>
            <a class="problem-title" href="${item.url}" target="_blank" rel="noreferrer">
              ${escapeHtml(item.name)}
            </a>
            <div class="tag-row">
              ${item.tags.slice(0, 5).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
            </div>
            <ul class="why-list">
              ${item.why.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}
            </ul>
            <div class="problem-footer">
              <span>score ${Math.round(item.score * 100)}</span>
              <span>match ${Math.round((item.features.content_similarity || 0) * 100)}%</span>
              <span>${item.solved_count.toLocaleString()} solves</span>
            </div>
          </article>
        `
      )
      .join("") || `<div class="empty-state">No recommendations matched the selected priority.</div>`;
}

function renderPlan(plan) {
  planGrid.innerHTML = plan.blocks
    .map(
      (block) => `
        <article class="plan-block">
          <h3>${escapeHtml(block.title)}</h3>
          <p>${escapeHtml(block.focus)}</p>
          <div class="mini-list">
            ${block.problems
              .map(
                (problem) => `
                  <a class="mini-problem" href="${problem.url}" target="_blank" rel="noreferrer">
                    <strong>${problem.rating}</strong>
                    <span>${escapeHtml(problem.name)}</span>
                  </a>
                `
              )
              .join("")}
          </div>
        </article>
      `
    )
    .join("");
}

function renderTopicTable(stats) {
  topicTable.innerHTML = stats
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.tag)}</td>
          <td><span class="level ${escapeHtml(item.level)}">${escapeHtml(item.level)}</span></td>
          <td>${item.attempted}</td>
          <td>${item.solved}</td>
          <td>${Math.round(item.acceptance_rate * 100)}%</td>
          <td>${item.avg_solved_rating || "-"}</td>
          <td>${Math.round(item.weakness_score * 100)}</td>
        </tr>
      `
    )
    .join("");
}

function renderEmptyState() {
  metricsGrid.innerHTML = `
    <div class="empty-state">Try your handle or a public handle such as tourist, Benq, or Petr.</div>
  `;
  evaluationGrid.innerHTML = "";
  growthGrid.innerHTML = "";
  recommendationGrid.innerHTML = "";
  planGrid.innerHTML = "";
  topicTable.innerHTML = "";
}

function renderError(error) {
  statusStrip.classList.remove("loading");
  refreshButton.disabled = currentHandle.length === 0;
  statusStrip.querySelector(".eyebrow").textContent = "Error";
  statusStrip.querySelector("strong").textContent = error.message;
}

function formatRank(rank) {
  return rank ? rank.replaceAll("_", " ") : "unrated";
}

function levelColor(level) {
  if (level === "weak") return chartColors.red;
  if (level === "strong") return chartColors.green;
  if (level === "unexplored") return chartColors.amber;
  return chartColors.blue;
}

function shortContest(name) {
  return name.replace("Codeforces Round", "Round").slice(0, 28);
}

function compactLanguage(language) {
  return language
    .replace("GNU C++", "C++")
    .replace("Microsoft Visual C++", "MSVC")
    .replace("PyPy", "PyPy");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function percent(value) {
  return value === null || value === undefined ? "-" : `${Math.round(value * 100)}%`;
}

function decimal(value) {
  return value === null || value === undefined ? "-" : Number(value).toFixed(3);
}

function signedNumber(value) {
  if (value === null || value === undefined) return "-";
  return value > 0 ? `+${value}` : String(value);
}
