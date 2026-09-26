const COOLDOWN_MS = 10 * 60 * 1000;

const params = new URLSearchParams(location.search);
const groupKey = params.get("g");

let lastRefreshedAt = null; // Date or null
let cooldownTimer = null;

const titleEl = document.getElementById("group-title");
const listEl = document.getElementById("article-list");
const statusEl = document.getElementById("status-line");
const refreshBtn = document.getElementById("refresh-btn");
const limitSelect = document.getElementById("limit-select");
const dateFrom = document.getElementById("date-from");
const dateTo = document.getElementById("date-to");
const keywordInput = document.getElementById("keyword-input");

if (!groupKey) {
  titleEl.textContent = "No group specified";
} else {
  init();
}

async function init() {
  const { data: group, error } = await supabaseClient
    .from("groups")
    .select("display_name, last_refreshed_at")
    .eq("key", groupKey)
    .maybeSingle();

  if (error || !group) {
    titleEl.textContent = "Group not found";
    return;
  }

  titleEl.textContent = group.display_name;
  lastRefreshedAt = group.last_refreshed_at ? new Date(group.last_refreshed_at) : null;
  updateCooldownUI();
  cooldownTimer = setInterval(updateCooldownUI, 15000);

  await loadArticles();

  limitSelect.addEventListener("change", loadArticles);
  document.getElementById("search-btn").addEventListener("click", loadArticles);
  document.getElementById("clear-btn").addEventListener("click", () => {
    dateFrom.value = "";
    dateTo.value = "";
    keywordInput.value = "";
    loadArticles();
  });
  keywordInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadArticles();
  });
  refreshBtn.addEventListener("click", onRefreshClick);
}

async function loadArticles() {
  const limit = parseInt(limitSelect.value, 10);
  let query = supabaseClient
    .from("articles")
    .select("title, url, source, published_at")
    .eq("group_key", groupKey)
    .lte("published_at", new Date().toISOString())
    .order("published_at", { ascending: false })
    .limit(limit);

  if (dateFrom.value) query = query.gte("published_at", `${dateFrom.value}T00:00:00Z`);
  if (dateTo.value) query = query.lte("published_at", `${dateTo.value}T23:59:59Z`);

  const keyword = keywordInput.value.trim();
  if (keyword) query = query.ilike("title", `%${keyword}%`);

  const { data, error } = await query;

  if (error) {
    listEl.innerHTML = `<li class="empty">Failed to load articles.</li>`;
    return;
  }

  if (!data.length) {
    listEl.innerHTML = `<li class="empty">No articles found.</li>`;
    return;
  }

  listEl.innerHTML = data
    .map((a) => {
      const date = new Date(a.published_at).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
      return `<li>
        <a href="${escapeAttr(a.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(a.title)}</a>
        <div class="article-meta">${escapeHtml(a.source)} &middot; ${date}</div>
      </li>`;
    })
    .join("");
}

function cooldownRemainingMs() {
  if (!lastRefreshedAt) return 0;
  const remaining = COOLDOWN_MS - (Date.now() - lastRefreshedAt.getTime());
  return Math.max(0, remaining);
}

function updateCooldownUI() {
  const remaining = cooldownRemainingMs();
  if (remaining > 0) {
    refreshBtn.disabled = true;
    const mins = Math.ceil(remaining / 60000);
    statusEl.textContent = lastRefreshedAt
      ? `Last updated ${relativeTime(lastRefreshedAt)}. You can refresh again in ~${mins} min.`
      : `You can refresh again in ~${mins} min.`;
  } else {
    refreshBtn.disabled = false;
    statusEl.textContent = lastRefreshedAt ? `Last updated ${relativeTime(lastRefreshedAt)}.` : "";
  }
}

function relativeTime(date) {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

async function onRefreshClick() {
  refreshBtn.disabled = true;
  statusEl.textContent = "Fetching latest news... this can take up to 20 seconds.";

  try {
    const resp = await fetch(`${SUPABASE_URL}/functions/v1/trigger-fetch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: SUPABASE_ANON_KEY,
        Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
      },
      body: JSON.stringify({ group_key: groupKey }),
    });
    const body = await resp.json();

    if (resp.status === 429) {
      lastRefreshedAt = new Date(Date.now() - (COOLDOWN_MS - body.retry_after_seconds * 1000));
      statusEl.textContent = `Please wait ~${Math.ceil(body.retry_after_seconds / 60)} min before refreshing again.`;
      updateCooldownUI();
      return;
    }

    if (!resp.ok) {
      statusEl.textContent = "Refresh failed. Try again later.";
      refreshBtn.disabled = false;
      return;
    }

    lastRefreshedAt = new Date();
    if (body.status === "timeout") {
      statusEl.textContent = "Still processing on GitHub's side -- showing what's available so far.";
    } else {
      statusEl.textContent = "Updated!";
    }
    await loadArticles();
    updateCooldownUI();
  } catch (err) {
    statusEl.textContent = "Refresh failed (network error). Try again later.";
    refreshBtn.disabled = false;
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function escapeAttr(s) {
  return escapeHtml(s);
}
