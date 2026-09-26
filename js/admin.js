let adminSession = null;

(async function guard() {
  const { data } = await supabaseClient.auth.getSession();
  if (!data.session) {
    location.href = "login.html";
    return;
  }
  adminSession = data.session;
  loadStatusPanel();
  loadManageGroups();
})();

document.getElementById("logout-btn").addEventListener("click", async () => {
  await supabaseClient.auth.signOut();
  location.href = "login.html";
});

const displayNameEl = document.getElementById("display-name");
const keyEl = document.getElementById("key");
let keyManuallyEdited = false;

keyEl.addEventListener("input", () => (keyManuallyEdited = true));
displayNameEl.addEventListener("input", () => {
  if (!keyManuallyEdited) keyEl.value = slugify(displayNameEl.value);
});

function slugify(s) {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.getElementById("add-group-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("add-error");
  const successEl = document.getElementById("add-success");
  errorEl.textContent = "";
  successEl.textContent = "";

  const displayName = displayNameEl.value.trim();
  const key = keyEl.value.trim();
  const extraTerms = document
    .getElementById("extra-terms")
    .value.split(",")
    .map((t) => t.trim())
    .filter(Boolean);

  if (!displayName || !key) {
    errorEl.textContent = "Group name and key are required.";
    return;
  }

  const { error } = await supabaseClient.from("groups").insert({
    key,
    display_name: displayName,
    search_patterns: [displayName, ...extraTerms],
    is_regex: false,
  });

  if (error) {
    errorEl.textContent = "Failed to add group: " + error.message;
    return;
  }

  successEl.textContent = `Added "${displayName}". It'll start picking up articles on the next fetch.`;
  e.target.reset();
  keyManuallyEdited = false;
  loadManageGroups();
});

// ---------- Status panel ----------

function relativeTime(date) {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

async function loadStatusPanel() {
  const panel = document.getElementById("status-panel");
  const { data: status } = await supabaseClient.from("fetch_status").select("*").eq("id", 1).maybeSingle();
  const { count: totalArticles } = await supabaseClient.from("articles").select("*", { count: "exact", head: true });

  let statusLine = "No scheduled fetch has completed yet.";
  if (status?.last_run_at) {
    const rel = relativeTime(new Date(status.last_run_at));
    statusLine =
      status.last_run_ok === false
        ? `<span class="error-text">Last run FAILED ${rel}: ${escapeHtml(status.last_error || "unknown error")}</span>`
        : `Last run succeeded ${rel}.`;
  }

  panel.innerHTML = `<p>${statusLine}</p><p class="hint">${totalArticles ?? 0} total articles stored.</p>`;
}

document.getElementById("trigger-all-btn").addEventListener("click", async () => {
  const btn = document.getElementById("trigger-all-btn");
  const statusEl = document.getElementById("trigger-all-status");
  btn.disabled = true;
  statusEl.textContent = "Fetching all groups... this can take a minute or two.";

  try {
    const resp = await fetch(`${SUPABASE_URL}/functions/v1/trigger-fetch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: SUPABASE_ANON_KEY,
        Authorization: `Bearer ${adminSession.access_token}`,
      },
      body: JSON.stringify({ all: true }),
    });
    const body = await resp.json();

    if (resp.status === 429) {
      statusEl.textContent = `Please wait ~${Math.ceil(body.retry_after_seconds / 60)} min before triggering again.`;
    } else if (!resp.ok) {
      statusEl.textContent = "Trigger failed: " + (body.error || resp.status);
    } else if (body.status === "timeout") {
      statusEl.textContent = "Still processing on GitHub's side -- check back shortly.";
    } else {
      statusEl.textContent = "Done!";
    }
  } catch (err) {
    statusEl.textContent = "Trigger failed (network error).";
  }

  btn.disabled = false;
  loadStatusPanel();
  loadManageGroups();
});

// ---------- Manage groups ----------

async function loadManageGroups() {
  const container = document.getElementById("manage-groups");
  const { data: groups, error } = await supabaseClient
    .from("groups")
    .select("key, display_name, search_patterns, last_refreshed_at")
    .order("display_name", { ascending: true });

  if (error || !groups) {
    container.innerHTML = `<p class="error-text">Failed to load groups.</p>`;
    return;
  }

  const counts = await Promise.all(
    groups.map((g) => supabaseClient.from("articles").select("*", { count: "exact", head: true }).eq("group_key", g.key)),
  );

  container.innerHTML = groups
    .map((g, i) => {
      const extraTerms = (g.search_patterns || []).filter((p) => p !== g.display_name).join(", ");
      const count = counts[i].count ?? 0;
      const lastRefreshed = g.last_refreshed_at ? relativeTime(new Date(g.last_refreshed_at)) : "never";
      return `
        <div class="manage-row" data-key="${escapeHtml(g.key)}">
          <input type="text" class="mg-display-name" value="${escapeHtml(g.display_name)}" />
          <input type="text" class="mg-extra-terms" value="${escapeHtml(extraTerms)}" placeholder="extra search terms, comma-separated" />
          <div class="hint">${count} articles &middot; last refreshed ${lastRefreshed}</div>
          <div class="manage-row-actions">
            <button class="mg-save">Save</button>
            <button class="mg-delete">Delete</button>
          </div>
          <p class="error-text mg-error"></p>
        </div>`;
    })
    .join("");

  container.querySelectorAll(".manage-row").forEach((row) => {
    const key = row.dataset.key;
    row.querySelector(".mg-save").addEventListener("click", () => saveGroup(row, key));
    row.querySelector(".mg-delete").addEventListener("click", () => deleteGroup(row, key));
  });
}

async function saveGroup(row, key) {
  const errorEl = row.querySelector(".mg-error");
  errorEl.textContent = "";

  const displayName = row.querySelector(".mg-display-name").value.trim();
  const extraTerms = row
    .querySelector(".mg-extra-terms")
    .value.split(",")
    .map((t) => t.trim())
    .filter(Boolean);

  if (!displayName) {
    errorEl.textContent = "Group name can't be empty.";
    return;
  }

  const { error } = await supabaseClient
    .from("groups")
    .update({ display_name: displayName, search_patterns: [displayName, ...extraTerms] })
    .eq("key", key);

  if (error) {
    errorEl.textContent = "Save failed: " + error.message;
    return;
  }
  loadManageGroups();
}

async function deleteGroup(row, key) {
  const displayName = row.querySelector(".mg-display-name").value;
  if (!confirm(`Delete "${displayName}" and all its articles? This can't be undone.`)) return;

  const { error } = await supabaseClient.from("groups").delete().eq("key", key);
  if (error) {
    row.querySelector(".mg-error").textContent = "Delete failed: " + error.message;
    return;
  }
  loadManageGroups();
}
