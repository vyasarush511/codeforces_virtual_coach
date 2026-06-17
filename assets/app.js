const CF_API = "https://codeforces.com/api";
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
  if (handle) analyze(handle);
});

refreshButton.addEventListener("click", () => {
  if (currentHandle) analyze(currentHandle);
});

window.addEventListener("load", () => {
  const params = new URLSearchParams(window.location.search);
  const handle = params.get("handle") || localStorage.getItem("lastHandle") || "";
  if (handle) {
    input.value = handle;
    analyze(handle);
  } else {
    renderEmptyState();
  }
  lucide.createIcons();
});

async function analyze(handle) {
  currentHandle = handle;
  localStorage.setItem("lastHandle", handle);
  setLoading(handle);
  try {
    const [userInfo, submissions, ratingHistory, problemset] = await Promise.all([
      cf("user.info", { handles: handle, checkHistoricHandles: "false" }),
      cf("user.status", { handle, from: 1, count: 10000 }),
      cf("user.rating", { handle }),
      cf("problemset.problems", {}),
    ]);
    const user = userInfo[0];
    const profile = buildUserProfile(user, submissions, ratingHistory);
    const catalog = buildProblemCatalog(problemset);
    const { recommendations, model } = recommendProblems(profile, catalog, 24);
    const evaluation = evaluateRecommender(user, submissions, ratingHistory, catalog, 10);
    const growthBacktest = evaluateGrowthBacktest(user, submissions, ratingHistory, catalog);
    currentData = {
      source: "Codeforces API",
      user: normalizeUser(user),
      profile: profile.summary,
      topic_stats: profile.topicStats.slice(0, 18),
      languages: profile.languages,
      timeline: profile.timeline,
      rating_history: normalizeRatingHistory(ratingHistory),
      recommender_model: model,
      evaluation,
      growth_backtest: growthBacktest,
      recommendations,
      plan: buildTrainingPlan(profile, recommendations),
      cache: { submissions_loaded: submissions.length, problem_catalog_size: catalog.length },
    };
    activePriority = "All";
    renderDashboard(currentData);
  } catch (error) {
    renderError(error);
  } finally {
    lucide.createIcons();
  }
}

async function cf(method, params) {
  const url = new URL(`${CF_API}/${method}`);
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value));
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Codeforces request failed: ${method}`);
  const payload = await response.json();
  if (payload.status !== "OK") throw new Error(payload.comment || `Codeforces error: ${method}`);
  return payload.result;
}

function buildUserProfile(user, submissions, ratingHistory) {
  const attempts = new Map();
  const solvedKeys = new Set();
  const activeDates = new Set();
  const solvedDates = new Set();
  const languages = new Map();
  const timeline = new Map();
  let acceptedSubmissions = 0;
  let rejectedSubmissions = 0;

  for (const submission of submissions) {
    const problem = submission.problem || {};
    const key = problemKey(problem);
    if (!key) continue;

    const createdAt = submission.creationTimeSeconds || 0;
    const date = utcDate(createdAt);
    const month = utcMonth(createdAt);
    activeDates.add(date);
    const verdict = submission.verdict || "UNKNOWN";
    const accepted = verdict === "OK";
    const language = submission.programmingLanguage || "Unknown";
    const languageStat = languages.get(language) || { language, submissions: 0, accepted: 0 };
    languageStat.submissions += 1;
    languages.set(language, languageStat);

    const monthStat = timeline.get(month) || { month, accepted: 0, rejected: 0, uniqueSolved: new Set() };
    timeline.set(month, monthStat);

    if (accepted) {
      acceptedSubmissions += 1;
      languageStat.accepted += 1;
      solvedKeys.add(key);
      solvedDates.add(date);
      monthStat.accepted += 1;
      monthStat.uniqueSolved.add(key);
    } else {
      rejectedSubmissions += 1;
      monthStat.rejected += 1;
    }

    const attempt = attempts.get(key) || {
      key,
      problem,
      accepted: false,
      attempts: 0,
      wrongAttempts: 0,
      firstAcceptedAt: null,
      latestSubmissionAt: createdAt,
    };
    attempt.attempts += 1;
    attempt.latestSubmissionAt = Math.max(attempt.latestSubmissionAt, createdAt);
    if (accepted) {
      attempt.accepted = true;
      if (!attempt.firstAcceptedAt) attempt.firstAcceptedAt = createdAt;
    } else {
      attempt.wrongAttempts += 1;
    }
    attempts.set(key, attempt);
  }

  const inferredRating = inferRating(user, submissions, ratingHistory);
  const topicStats = buildTopicStats(attempts, inferredRating);
  const solvedRatings = Array.from(attempts.values())
    .filter((attempt) => attempt.accepted && attempt.problem.rating)
    .map((attempt) => Number(attempt.problem.rating));
  const weakTags = topicStats
    .filter((stat) => stat.level === "weak" || stat.level === "unexplored")
    .slice(0, 6)
    .map((stat) => stat.tag);
  const strongTags = topicStats
    .filter((stat) => stat.level === "strong")
    .sort((a, b) => b.acceptance_rate - a.acceptance_rate)
    .slice(0, 6)
    .map((stat) => stat.tag);

  return {
    summary: {
      solved_count: solvedKeys.size,
      attempted_count: attempts.size,
      accepted_submissions: acceptedSubmissions,
      rejected_submissions: rejectedSubmissions,
      active_days: activeDates.size,
      best_solved_rating: solvedRatings.length ? Math.max(...solvedRatings) : null,
      avg_solved_rating: solvedRatings.length ? round(avg(solvedRatings), 1) : null,
      current_streak_days: currentStreak(solvedDates),
      max_streak_days: maxStreak(solvedDates),
      inferred_rating: inferredRating,
      strong_tags: strongTags,
      weak_tags: weakTags,
    },
    topicStats,
    languages: Array.from(languages.values())
      .map((item) => ({ ...item, acceptance_rate: item.submissions ? item.accepted / item.submissions : 0 }))
      .sort((a, b) => b.submissions - a.submissions)
      .slice(0, 10),
    timeline: Array.from(timeline.values())
      .sort((a, b) => a.month.localeCompare(b.month))
      .slice(-18)
      .map((item) => ({
        month: item.month,
        accepted: item.accepted,
        rejected: item.rejected,
        unique_solved: item.uniqueSolved.size,
      })),
    solvedKeys,
    attemptedKeys: new Set(attempts.keys()),
  };
}

function buildTopicStats(attempts, inferredRating) {
  const topic = new Map();
  for (const [key, attempt] of attempts) {
    const tags = attempt.problem.tags?.length ? attempt.problem.tags : ["untagged"];
    for (const tag of tags) {
      const stat = topic.get(tag) || {
        tag,
        attemptedKeys: new Set(),
        solvedKeys: new Set(),
        wrong_attempts: 0,
        solvedRatings: [],
        latestSolveAt: null,
      };
      stat.attemptedKeys.add(key);
      stat.wrong_attempts += attempt.wrongAttempts;
      if (attempt.accepted) {
        stat.solvedKeys.add(key);
        if (attempt.problem.rating) stat.solvedRatings.push(Number(attempt.problem.rating));
        if (attempt.firstAcceptedAt && (!stat.latestSolveAt || attempt.firstAcceptedAt > stat.latestSolveAt)) {
          stat.latestSolveAt = attempt.firstAcceptedAt;
        }
      }
      topic.set(tag, stat);
    }
  }

  return Array.from(topic.values())
    .map((raw) => {
      const attempted = raw.attemptedKeys.size;
      const solved = raw.solvedKeys.size;
      const acceptanceRate = attempted ? solved / attempted : 0;
      const avgSolvedRating = raw.solvedRatings.length ? avg(raw.solvedRatings) : null;
      const confidence = clamp(Math.log1p(attempted) / Math.log1p(30));
      const weakness = weaknessScore(attempted, solved, raw.wrong_attempts, acceptanceRate, avgSolvedRating, inferredRating, confidence);
      const level = topicLevel(attempted, solved, acceptanceRate, avgSolvedRating, inferredRating, weakness);
      return {
        tag: raw.tag,
        attempted,
        solved,
        wrong_attempts: raw.wrong_attempts,
        acceptance_rate: round(acceptanceRate, 4),
        avg_solved_rating: avgSolvedRating === null ? null : round(avgSolvedRating, 1),
        max_solved_rating: raw.solvedRatings.length ? Math.max(...raw.solvedRatings) : null,
        latest_solve_at: raw.latestSolveAt ? utcDate(raw.latestSolveAt) : null,
        weakness_score: round(weakness, 4),
        confidence: round(confidence, 4),
        level,
      };
    })
    .sort((a, b) => b.weakness_score - a.weakness_score || b.attempted - a.attempted);
}

function buildProblemCatalog(problemset) {
  const stats = new Map();
  for (const item of problemset.problemStatistics || []) {
    const key = `${item.contestId}${item.index}`;
    stats.set(key, item.solvedCount || 0);
  }
  return (problemset.problems || [])
    .filter((problem) => problem.contestId && problem.index && problem.rating && !hasCyrillic(problem.name || ""))
    .map((problem) => {
      const key = `${problem.contestId}${problem.index}`;
      return {
        key,
        contest_id: problem.contestId,
        index: problem.index,
        name: problem.name,
        rating: problem.rating,
        tags: problem.tags || [],
        solved_count: stats.get(key) || 0,
        url: `https://codeforces.com/problemset/problem/${problem.contestId}/${problem.index}`,
      };
    });
}

function hasCyrillic(text) {
  return /[\u0400-\u04FF]/.test(text);
}

function recommendProblems(profile, catalog, topN) {
  const userRating = profile.summary.inferred_rating;
  const weakTags = new Set(profile.summary.weak_tags);
  const topicByTag = Object.fromEntries(profile.topicStats.map((stat) => [stat.tag, stat]));
  const maxSolvedCount = Math.max(1, ...catalog.map((problem) => problem.solved_count));
  const contentScores = contentSimilarityScores(profile, catalog);

  const candidates = [];
  for (const problem of catalog) {
    if (profile.solvedKeys.has(problem.key)) continue;
    if (!insideCandidateBand(problem.rating, userRating, weakTags, problem.tags)) continue;
    const features = scoreFeatures(problem, userRating, profile.attemptedKeys.has(problem.key), weakTags, topicByTag, maxSolvedCount);
    features.content_similarity = contentScores[problem.key] || 0;
    features.rule_score =
      0.4 * features.tag_weakness +
      0.28 * features.difficulty_fit +
      0.16 * features.popularity +
      0.1 * features.undertrained_tag +
      0.06 * features.retry_value;
    const score = 0.58 * features.rule_score + 0.34 * features.content_similarity + 0.08 * features.freshness;
    candidates.push({
      ...problem,
      score: round(score, 4),
      difficulty_fit: round(features.difficulty_fit, 4),
      priority: priority(problem, userRating, weakTags, profile.attemptedKeys.has(problem.key)),
      why: explain(problem, userRating, weakTags, topicByTag, profile.attemptedKeys.has(problem.key), features.content_similarity),
      features: Object.fromEntries(Object.entries(features).map(([key, value]) => [key, round(value, 4)])),
    });
  }

  const selected = diversify(candidates.sort((a, b) => b.score - a.score).slice(0, 300), topN);
  return {
    recommendations: selected.map(({ key, ...rest }) => rest),
    model: {
      name: "Stage 2 Content-Based Recommender",
      status: "active",
      method: "Cosine similarity + KNN over problem vectors",
      focus_tags: profile.summary.weak_tags.slice(0, 5),
      candidate_count: catalog.length,
    },
  };
}

function evaluateRecommender(user, submissions, ratingHistory, catalog, k) {
  const solvedEvents = firstSolveEvents(submissions);
  if (solvedEvents.length < 20) {
    return {
      status: "insufficient_history",
      k,
      message: "Need at least 20 solved problems for temporal backtesting.",
      train_solved: solvedEvents.length,
      holdout_solved: 0,
      precision_at_k: null,
      hit_rate_at_k: null,
      ndcg_at_k: null,
      mrr: null,
      hits: [],
    };
  }

  let splitIndex = Math.floor(solvedEvents.length * 0.8);
  splitIndex = Math.max(1, Math.min(splitIndex, solvedEvents.length - 1));
  const cutoff = solvedEvents[splitIndex - 1].acceptedAt;
  const holdoutKeys = new Set(solvedEvents.slice(splitIndex).map((event) => event.key));
  const trainingSubmissions = submissions.filter((submission) => (submission.creationTimeSeconds || 0) <= cutoff);
  const trainingRating = ratingHistory.filter((item) => (item.ratingUpdateTimeSeconds || 0) <= cutoff);
  const trainingProfile = buildUserProfile(user, trainingSubmissions, trainingRating);
  const { recommendations } = recommendProblems(trainingProfile, catalog, k);
  const recommendedKeys = recommendations.slice(0, k).map((item) => `${item.contest_id}${item.index}`);
  const hits = recommendedKeys.filter((key) => holdoutKeys.has(key));

  return {
    status: "ok",
    k,
    cutoff_date: utcDate(cutoff),
    train_solved: splitIndex,
    holdout_solved: holdoutKeys.size,
    precision_at_k: round(hits.length / k, 4),
    hit_rate_at_k: hits.length ? 1 : 0,
    ndcg_at_k: round(ndcg(recommendedKeys, holdoutKeys, k), 4),
    mrr: round(mrr(recommendedKeys, holdoutKeys), 4),
    hits,
  };
}

function evaluateGrowthBacktest(user, submissions, ratingHistory, catalog, windowDays = 60, maxCheckpoints = 6) {
  if (ratingHistory.length < 4) {
    return insufficientGrowth("insufficient_rating_history", "Need at least 4 rated contests for growth backtesting.", windowDays);
  }
  const windows = [];
  for (const event of sampleCheckpoints(ratingHistory, maxCheckpoints)) {
    const cutoff = event.ratingUpdateTimeSeconds || 0;
    const endTime = cutoff + windowDays * 86400;
    const futureRatingEvents = ratingHistory.filter((item) => cutoff < (item.ratingUpdateTimeSeconds || 0) && (item.ratingUpdateTimeSeconds || 0) <= endTime);
    if (!futureRatingEvents.length) continue;

    const trainingSubmissions = submissions.filter((submission) => (submission.creationTimeSeconds || 0) <= cutoff);
    const futureSolves = uniqueAcceptedBetween(submissions, cutoff, endTime);
    if (futureSolves.length < 3) continue;

    const trainingRating = ratingHistory.filter((item) => (item.ratingUpdateTimeSeconds || 0) <= cutoff);
    const trainingProfile = buildUserProfile(user, trainingSubmissions, trainingRating);
    if (trainingProfile.summary.solved_count < 20) continue;

    const { recommendations } = recommendProblems(trainingProfile, catalog, 20);
    const focusTags = trainingProfile.summary.weak_tags.slice(0, 4);
    const activeFocusTags = focusTags.length ? focusTags : topRecommendationTags(recommendations);
    if (!activeFocusTags.length) continue;

    const recRatings = recommendations.map((item) => item.rating).filter(Boolean);
    const lowRating = recRatings.length ? Math.min(...recRatings) - 100 : Math.max(800, event.newRating - 250);
    const highRating = recRatings.length ? Math.max(...recRatings) + 100 : event.newRating + 500;
    const alignedSolves = futureSolves.filter((submission) => matchesFocus(submission, activeFocusTags, lowRating, highRating));
    const adherence = alignedSolves.length / futureSolves.length;
    const beforeSkill = avgSolvedRatingForTags(trainingSubmissions, activeFocusTags);
    const afterSkill = avgSolvedRatingForTags(futureSolves, activeFocusTags);
    const skillGain = beforeSkill !== null && afterSkill !== null ? afterSkill - beforeSkill : null;

    windows.push({
      cutoff_date: utcDate(cutoff),
      rating_delta: futureRatingEvents.at(-1).newRating - event.newRating,
      future_solves: futureSolves.length,
      aligned_solves: alignedSolves.length,
      focus_adherence: adherence,
      followed: adherence >= 0.25,
      weak_tag_skill_gain: skillGain,
      focus_tags: activeFocusTags,
    });
  }

  if (!windows.length) {
    return insufficientGrowth("insufficient_windows", "Not enough future solve/rating windows to estimate growth.", windowDays);
  }

  const followed = windows.filter((window) => window.followed);
  const baseline = windows.filter((window) => !window.followed);
  const followedDelta = meanOrNull(followed.map((window) => window.rating_delta));
  const baselineDelta = meanOrNull(baseline.map((window) => window.rating_delta));
  const uplift = followedDelta !== null && baselineDelta !== null ? followedDelta - baselineDelta : null;

  return {
    status: "ok",
    window_days: windowDays,
    windows_evaluated: windows.length,
    followed_windows: followed.length,
    baseline_windows: baseline.length,
    avg_rating_delta_followed: roundOrNull(followedDelta, 1),
    avg_rating_delta_baseline: roundOrNull(baselineDelta, 1),
    estimated_rating_uplift: roundOrNull(uplift, 1),
    avg_focus_adherence: roundOrNull(meanOrNull(windows.map((window) => window.focus_adherence)), 4),
    avg_weak_tag_skill_gain: roundOrNull(meanOrNull(windows.map((window) => window.weak_tag_skill_gain).filter((value) => value !== null)), 1),
    windows,
    note: "Growth backtest is correlational, not causal; it estimates whether recommendation-aligned practice historically coincided with stronger outcomes.",
  };
}

function insufficientGrowth(status, message, windowDays) {
  return {
    status,
    message,
    window_days: windowDays,
    windows_evaluated: 0,
    followed_windows: 0,
    baseline_windows: 0,
    avg_rating_delta_followed: null,
    avg_rating_delta_baseline: null,
    estimated_rating_uplift: null,
    avg_focus_adherence: null,
    avg_weak_tag_skill_gain: null,
  };
}

function sampleCheckpoints(ratingHistory, maxCheckpoints) {
  const eligible = ratingHistory.slice(1, -1);
  if (eligible.length <= maxCheckpoints) return eligible;
  const step = Math.max(1, Math.floor(eligible.length / maxCheckpoints));
  return eligible.filter((_, index) => index % step === 0).slice(0, maxCheckpoints);
}

function uniqueAcceptedBetween(submissions, startTime, endTime) {
  const firstByKey = new Map();
  for (const submission of submissions) {
    if (submission.verdict !== "OK") continue;
    const createdAt = submission.creationTimeSeconds || 0;
    if (!(startTime < createdAt && createdAt <= endTime)) continue;
    const key = problemKey(submission.problem || {});
    if (!key) continue;
    const current = firstByKey.get(key);
    if (!current || createdAt < (current.creationTimeSeconds || 0)) firstByKey.set(key, submission);
  }
  return Array.from(firstByKey.values());
}

function matchesFocus(submission, focusTags, lowRating, highRating) {
  const problem = submission.problem || {};
  const rating = problem.rating;
  if (!rating || rating < lowRating || rating > highRating) return false;
  return problem.tags?.some((tag) => focusTags.includes(tag)) || false;
}

function avgSolvedRatingForTags(submissions, tags) {
  const tagSet = new Set(tags);
  const ratings = submissions
    .filter((submission) => submission.verdict === "OK" && submission.problem?.rating && submission.problem?.tags?.some((tag) => tagSet.has(tag)))
    .map((submission) => Number(submission.problem.rating));
  return ratings.length ? avg(ratings) : null;
}

function topRecommendationTags(recommendations) {
  const counts = {};
  recommendations.slice(0, 10).forEach((recommendation) => {
    recommendation.tags.forEach((tag) => {
      counts[tag] = (counts[tag] || 0) + 1;
    });
  });
  return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([tag]) => tag);
}

function firstSolveEvents(submissions) {
  const firstByKey = new Map();
  for (const submission of submissions) {
    if (submission.verdict !== "OK") continue;
    const key = problemKey(submission.problem || {});
    if (!key) continue;
    const acceptedAt = submission.creationTimeSeconds || 0;
    const current = firstByKey.get(key);
    if (!current || acceptedAt < current.acceptedAt) {
      firstByKey.set(key, { key, acceptedAt });
    }
  }
  return Array.from(firstByKey.values()).sort((a, b) => a.acceptedAt - b.acceptedAt);
}

function ndcg(recommendedKeys, relevantKeys, k) {
  let dcg = 0;
  recommendedKeys.slice(0, k).forEach((key, index) => {
    if (relevantKeys.has(key)) dcg += 1 / Math.log2(index + 2);
  });
  const idealHits = Math.min(k, relevantKeys.size);
  let idcg = 0;
  for (let index = 1; index <= idealHits; index++) {
    idcg += 1 / Math.log2(index + 1);
  }
  return idcg ? dcg / idcg : 0;
}

function mrr(recommendedKeys, relevantKeys) {
  const index = recommendedKeys.findIndex((key) => relevantKeys.has(key));
  return index >= 0 ? 1 / (index + 1) : 0;
}

function contentSimilarityScores(profile, catalog) {
  const userVector = userNeedVector(profile);
  const raw = catalog.map((problem) => [problem.key, cosine(problemVector(problem), userVector)]);
  const values = raw.map(([, score]) => score);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const normalized = Object.fromEntries(raw.map(([key, score]) => [key, max > min ? (score - min) / (max - min) : score]));
  const nearest = [...raw].sort((a, b) => b[1] - a[1]).slice(0, 50);
  nearest.forEach(([key], index) => {
    normalized[key] = clamp(0.82 * normalized[key] + 0.18 * (1 - index / 50));
  });
  return normalized;
}

function problemVector(problem) {
  const vector = {
    rating_scaled: problem.rating / 4000,
    popularity: Math.log1p(problem.solved_count) / 12,
    recency: clamp((problem.contest_id - 900) / 1400),
    [`rating_bucket=${Math.floor(problem.rating / 100) * 100}`]: 1,
  };
  problem.tags.forEach((tag) => (vector[`tag=${tag}`] = 1));
  return vector;
}

function userNeedVector(profile) {
  const targetRating = profile.summary.inferred_rating + 150;
  const topicByTag = Object.fromEntries(profile.topicStats.map((stat) => [stat.tag, stat]));
  const vector = {
    rating_scaled: targetRating / 4000,
    popularity: 0.72,
    recency: 0.62,
    [`rating_bucket=${Math.floor(targetRating / 100) * 100}`]: 1,
  };
  profile.summary.weak_tags.slice(0, 6).forEach((tag) => {
    vector[`tag=${tag}`] = clamp(0.35 + (topicByTag[tag]?.weakness_score || 0.5));
  });
  return vector;
}

function scoreFeatures(problem, userRating, attempted, weakTags, topicByTag, maxSolvedCount) {
  const tagWeaknessValues = problem.tags.map((tag) => topicByTag[tag]?.weakness_score ?? 0.32);
  const tagWeakness = tagWeaknessValues.length ? Math.max(...tagWeaknessValues) : 0.2;
  const weakOverlap = intersectionSize(weakTags, problem.tags) / Math.max(1, problem.tags.length);
  const undertrained = problem.tags.map((tag) => 1 - Math.min(1, (topicByTag[tag]?.attempted || 0) / 12));
  return {
    tag_weakness: clamp(0.75 * tagWeakness + 0.25 * weakOverlap),
    difficulty_fit: difficultyFit(problem.rating, userRating),
    popularity: clamp(Math.log1p(problem.solved_count) / Math.log1p(maxSolvedCount)),
    undertrained_tag: undertrained.length ? Math.max(...undertrained) : 0.25,
    retry_value: attempted ? 1 : 0,
    freshness: clamp((problem.contest_id - 900) / 1400),
  };
}

function buildTrainingPlan(profile, recommendations) {
  const rating = profile.summary.inferred_rating;
  const nextTarget = (Math.floor(rating / 100) + 2) * 100;
  const core = recommendations.filter((item) => item.priority === "Core" || item.priority === "Repair");
  const stretch = recommendations.filter((item) => item.priority === "Stretch");
  const explore = recommendations.filter((item) => item.priority === "Explore");
  const today = (core.length ? core : recommendations).slice(0, 3);
  const week = uniqueByProblem([...core.slice(3), ...explore, ...recommendations], today).slice(0, 7);
  const stretchBlock = uniqueByProblem([...stretch, ...recommendations], [...today, ...week]).slice(0, 3);
  return {
    current_band: `${Math.floor(rating / 100) * 100}-${(Math.floor(rating / 100) + 1) * 100}`,
    next_target_rating: nextTarget,
    weekly_load: today.length + week.length,
    focus_tags: profile.summary.weak_tags.slice(0, 4),
    blocks: [
      { title: "Today", focus: `Repair and sharpen ${(profile.summary.weak_tags.slice(0, 3).join(", ") || "mixed fundamentals")}`, problems: today },
      { title: "This week", focus: "Build volume without leaving the rating-growth band", problems: week },
      { title: "Stretch", focus: `Probe readiness for ${nextTarget}`, problems: stretchBlock },
    ],
    milestones: [],
  };
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
    .map(([label, value, hint]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(hint)}</small></article>`)
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
    .map(([label, value, hint]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(hint)}</small></article>`)
    .join("");
}

function renderGrowthBacktest(growth) {
  if (!growth || growth.status !== "ok") {
    growthGrid.innerHTML = `<div class="empty-state">${escapeHtml(growth?.message || "Not enough rating history to estimate growth outcomes.")}</div>`;
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
    .map(([label, value, hint]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(hint)}</small></article>`)
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
    data: { labels: stats.map((x) => x.tag), datasets: [{ label: "Weakness", data: stats.map((x) => Math.round(x.weakness_score * 100)), backgroundColor: stats.map((x) => levelColor(x.level)), borderRadius: 6 }] },
    options: baseChartOptions({ indexAxis: "y", scales: { x: { min: 0, max: 100, grid: { color: "#eef1f4" } }, y: { grid: { display: false } } } }),
  });
}

function drawRatingChart(history) {
  replaceChart("rating", "rating-chart", {
    type: "line",
    data: { labels: history.map((x) => shortContest(x.contest_name)), datasets: [{ label: "Rating", data: history.map((x) => x.new_rating), borderColor: chartColors.blue, backgroundColor: "rgba(53, 99, 233, 0.12)", fill: true, tension: 0.32, pointRadius: 2 }] },
    options: baseChartOptions({ scales: { x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { display: false } }, y: { grid: { color: "#eef1f4" } } } }),
  });
}

function drawTimelineChart(timeline) {
  replaceChart("timeline", "timeline-chart", {
    type: "bar",
    data: { labels: timeline.map((x) => x.month), datasets: [{ label: "Accepted", data: timeline.map((x) => x.accepted), backgroundColor: chartColors.green, borderRadius: 5 }, { label: "Rejected", data: timeline.map((x) => x.rejected), backgroundColor: chartColors.red, borderRadius: 5 }] },
    options: baseChartOptions({ scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, grid: { color: "#eef1f4" } } } }),
  });
}

function drawLanguageChart(languages) {
  replaceChart("language", "language-chart", {
    type: "doughnut",
    data: { labels: languages.map((x) => compactLanguage(x.language)), datasets: [{ data: languages.map((x) => x.accepted), backgroundColor: [chartColors.blue, chartColors.green, chartColors.amber, chartColors.violet, chartColors.red, "#506070"], borderWidth: 0 }] },
    options: baseChartOptions({ cutout: "62%", plugins: { legend: { position: "bottom", labels: { boxWidth: 12, color: chartColors.gray } } } }),
  });
}

function renderFilters(recommendations) {
  const priorities = ["All", ...Array.from(new Set(recommendations.map((x) => x.priority)))];
  priorityFilters.innerHTML = priorities.map((p) => `<button class="pill ${p === activePriority ? "active" : ""}" type="button" data-priority="${escapeHtml(p)}">${escapeHtml(p)}</button>`).join("");
  priorityFilters.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activePriority = button.dataset.priority;
      renderFilters(currentData.recommendations);
      renderRecommendations(currentData.recommendations);
    });
  });
}

function renderRecommendations(recommendations) {
  const visible = activePriority === "All" ? recommendations : recommendations.filter((x) => x.priority === activePriority);
  recommendationGrid.innerHTML = visible.map((item) => `
    <article class="problem-card">
      <div class="problem-topline"><span class="badge ${escapeHtml(item.priority)}">${escapeHtml(item.priority)}</span><strong>${item.rating}</strong></div>
      <a class="problem-title" href="${item.url}" target="_blank" rel="noreferrer">${escapeHtml(item.name)}</a>
      <div class="tag-row">${item.tags.slice(0, 5).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
      <ul class="why-list">${item.why.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>
      <div class="problem-footer"><span>score ${Math.round(item.score * 100)}</span><span>match ${Math.round((item.features.content_similarity || 0) * 100)}%</span><span>${item.solved_count.toLocaleString()} solves</span></div>
    </article>`).join("") || `<div class="empty-state">No recommendations matched the selected priority.</div>`;
}

function renderPlan(plan) {
  planGrid.innerHTML = plan.blocks.map((block) => `
    <article class="plan-block">
      <h3>${escapeHtml(block.title)}</h3>
      <p>${escapeHtml(block.focus)}</p>
      <div class="mini-list">${block.problems.map((problem) => `<a class="mini-problem" href="${problem.url}" target="_blank" rel="noreferrer"><strong>${problem.rating}</strong><span>${escapeHtml(problem.name)}</span></a>`).join("")}</div>
    </article>`).join("");
}

function renderTopicTable(stats) {
  topicTable.innerHTML = stats.map((item) => `
    <tr>
      <td>${escapeHtml(item.tag)}</td><td><span class="level ${escapeHtml(item.level)}">${escapeHtml(item.level)}</span></td>
      <td>${item.attempted}</td><td>${item.solved}</td><td>${Math.round(item.acceptance_rate * 100)}%</td>
      <td>${item.avg_solved_rating || "-"}</td><td>${Math.round(item.weakness_score * 100)}</td>
    </tr>`).join("");
}

function setLoading(handle) {
  statusStrip.classList.add("loading");
  refreshButton.disabled = true;
  statusStrip.querySelector(".eyebrow").textContent = "Analyzing";
  statusStrip.querySelector("strong").textContent = `Building profile for ${handle}`;
}

function renderEmptyState() {
  metricsGrid.innerHTML = `<div class="empty-state">Try your handle or a public handle such as tourist, Benq, or Petr.</div>`;
  evaluationGrid.innerHTML = "";
  growthGrid.innerHTML = "";
}

function renderError(error) {
  statusStrip.classList.remove("loading");
  refreshButton.disabled = currentHandle.length === 0;
  statusStrip.querySelector(".eyebrow").textContent = "Error";
  statusStrip.querySelector("strong").textContent = error.message;
}

function normalizeUser(user) {
  return { handle: user.handle, rating: user.rating, rank: user.rank, max_rating: user.maxRating, max_rank: user.maxRank };
}

function normalizeRatingHistory(history) {
  return history.slice(-30).map((item) => ({
    contest_id: item.contestId,
    contest_name: item.contestName,
    rank: item.rank,
    old_rating: item.oldRating,
    new_rating: item.newRating,
    rating_update_time_seconds: item.ratingUpdateTimeSeconds,
  }));
}

function weaknessScore(attempted, solved, wrongAttempts, acceptanceRate, avgSolvedRating, inferredRating, confidence) {
  const ratingGap = avgSolvedRating === null ? 0.65 : clamp((inferredRating + 150 - avgSolvedRating) / 900);
  const raw = 0.34 * (1 - acceptanceRate) + 0.24 * ratingGap + 0.18 / Math.sqrt(attempted + 1) + 0.16 * clamp(wrongAttempts / Math.max(3, attempted * 3)) + (attempted >= 3 && solved === 0 ? 0.2 : 0);
  return clamp(raw * (0.58 + 0.42 * confidence));
}

function topicLevel(attempted, solved, acceptanceRate, avgRating, inferredRating, weakness) {
  if (attempted <= 2) return "unexplored";
  if (solved >= 8 && acceptanceRate >= 0.68 && (avgRating || 0) >= inferredRating - 250) return "strong";
  if (weakness >= 0.52) return "weak";
  return "developing";
}

function inferRating(user, submissions, ratingHistory) {
  if (user.rating) return user.rating;
  if (ratingHistory.length) return ratingHistory.at(-1).newRating;
  const solvedRatings = submissions.filter((s) => s.verdict === "OK" && s.problem?.rating).map((s) => Number(s.problem.rating));
  return solvedRatings.length ? Math.round((avg(solvedRatings) + 200) / 100) * 100 : 1200;
}

function priority(problem, userRating, weakTags, attempted) {
  if (attempted) return "Repair";
  if (problem.rating >= userRating + 300) return "Stretch";
  if (intersectionSize(weakTags, problem.tags)) return "Core";
  return "Explore";
}

function explain(problem, userRating, weakTags, topicByTag, attempted, contentSimilarity) {
  const reasons = [];
  const overlap = problem.tags.filter((tag) => weakTags.has(tag));
  if (overlap.length) {
    const tag = overlap.sort((a, b) => (topicByTag[b]?.weakness_score || 0) - (topicByTag[a]?.weakness_score || 0))[0];
    reasons.push(`Targets ${tag}: ${Math.round((topicByTag[tag]?.acceptance_rate || 0) * 100)}% solve rate across attempted problems`);
  }
  if (attempted) reasons.push("Already attempted but not solved, making it a high-value repair problem");
  const gap = problem.rating - userRating;
  if (gap >= -100 && gap <= 250) reasons.push("Sits in the optimal growth band for your current rating");
  else if (gap > 250) reasons.push("Stretch problem for rating-upside practice");
  if (contentSimilarity >= 0.68) reasons.push("High content match to your weakness vector");
  if (problem.solved_count >= 1000) reasons.push("Popular enough to have reliable editorials and community discussion");
  return reasons.slice(0, 3);
}

function diversify(candidates, topN) {
  const selected = [];
  const remaining = [...candidates];
  while (remaining.length && selected.length < topN) {
    let bestIndex = 0;
    let bestScore = -1;
    remaining.forEach((candidate, index) => {
      const adjusted = candidate.score - diversityPenalty(candidate, selected);
      if (adjusted > bestScore) {
        bestScore = adjusted;
        bestIndex = index;
      }
    });
    selected.push(remaining.splice(bestIndex, 1)[0]);
  }
  return selected;
}

function diversityPenalty(candidate, selected) {
  let penalty = 0;
  for (const item of selected) {
    const c = new Set(candidate.tags);
    const i = new Set(item.tags);
    const union = new Set([...c, ...i]).size || 1;
    const overlap = intersectionSize(c, item.tags) / union;
    penalty = Math.max(penalty, 0.09 * overlap + (Math.abs(candidate.rating - item.rating) <= 100 ? 0.006 : 0));
  }
  return penalty;
}

function insideCandidateBand(rating, userRating, weakTags, tags) {
  const low = Math.max(800, userRating - 250);
  const high = userRating + 500;
  return (rating >= low && rating <= high) || (intersectionSize(weakTags, tags) && rating >= low && rating <= high + 150);
}

function difficultyFit(problemRating, userRating) {
  const target = userRating + 125;
  const sigma = 285;
  return clamp(Math.exp(-((problemRating - target) ** 2) / (2 * sigma * sigma)));
}

function replaceChart(key, elementId, config) {
  if (charts[key]) charts[key].destroy();
  charts[key] = new Chart(document.querySelector(`#${elementId}`), config);
}

function baseChartOptions(extra = {}) {
  return { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, labels: { color: chartColors.gray, boxWidth: 12 } }, tooltip: { intersect: false, mode: "index" }, ...(extra.plugins || {}) }, ...extra };
}

function cosine(a, b) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  let dot = 0;
  let normA = 0;
  let normB = 0;
  keys.forEach((key) => {
    const av = a[key] || 0;
    const bv = b[key] || 0;
    dot += av * bv;
    normA += av * av;
    normB += bv * bv;
  });
  return normA && normB ? dot / (Math.sqrt(normA) * Math.sqrt(normB)) : 0;
}

function uniqueByProblem(items, exclude = []) {
  const seen = new Set(exclude.map((item) => `${item.contest_id}${item.index}`));
  return items.filter((item) => {
    const key = `${item.contest_id}${item.index}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function currentStreak(dates) {
  return maxStreak(dates);
}

function maxStreak(dates) {
  if (!dates.size) return 0;
  const sorted = Array.from(dates).sort();
  let best = 1;
  let current = 1;
  for (let i = 1; i < sorted.length; i++) {
    const diff = (new Date(sorted[i]) - new Date(sorted[i - 1])) / 86400000;
    current = diff === 1 ? current + 1 : 1;
    best = Math.max(best, current);
  }
  return best;
}

function problemKey(problem) {
  return problem.contestId && problem.index ? `${problem.contestId}${problem.index}` : null;
}

function utcDate(timestamp) {
  return new Date(timestamp * 1000).toISOString().slice(0, 10);
}

function utcMonth(timestamp) {
  return new Date(timestamp * 1000).toISOString().slice(0, 7);
}

function avg(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function round(value, decimals = 4) {
  return Number(value.toFixed(decimals));
}

function clamp(value, low = 0, high = 1) {
  return Math.max(low, Math.min(high, value));
}

function intersectionSize(set, values) {
  return values.filter((value) => set.has(value)).length;
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
  return language.replace("GNU C++", "C++").replace("Microsoft Visual C++", "MSVC").replace("PyPy", "PyPy");
}

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
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

function meanOrNull(values) {
  return values.length ? avg(values) : null;
}

function roundOrNull(value, decimals) {
  return value === null || value === undefined ? null : round(value, decimals);
}
