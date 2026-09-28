let adminSession = null;

(async function guard() {
  const { data } = await supabaseClient.auth.getSession();
  if (!data.session) {
    location.href = "login.html";
    return;
  }
  adminSession = data.session;
  loadStatusPanel();
  loadSettings();
  loadManageGroups();
  loadFeedbackPanel();
})();

document.getElementById("logout-btn").addEventListener("click", async () => {
  await supabaseClient.auth.signOut();
  location.href = "login.html";
});

const displayNameEl = document.getElementById("display-name");

document.getElementById("lookup-members-btn").addEventListener("click", async () => {
  const btn = document.getElementById("lookup-members-btn");
  const statusEl = document.getElementById("lookup-status");
  const name = displayNameEl.value.trim();

  if (!name) {
    statusEl.textContent = "Type the group name first.";
    return;
  }

  btn.disabled = true;
  statusEl.textContent = "Looking up members on Wikipedia...";

  try {
    const members = await lookupMembersFromWikipedia(name);
    if (members.length === 0) {
      statusEl.textContent = "Couldn't auto-detect members -- add them manually above.";
    } else {
      document.getElementById("extra-terms").value = members.join(", ");
      statusEl.textContent = `Found ${members.length} member(s) -- double-check before saving.`;
    }
  } catch (err) {
    statusEl.textContent = "Lookup failed (network error) -- add members manually.";
  }

  btn.disabled = false;
});

function slugify(s) {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function splitTerms(value) {
  return value.split(",").map((t) => t.trim()).filter(Boolean);
}

// Case-insensitive de-dupe, keeping the first spelling.
function uniqueTerms(terms) {
  const seen = new Set();
  return terms.filter((t) => {
    const k = plainTerm(t).toLowerCase();
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

// Regex groups store terms like "\bSKZ\b" -- this is the readable form.
function plainTerm(p) {
  return p.replace(/\\b/g, "").replace(/\\/g, "");
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
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
  const key = slugify(displayName);
  const extraTerms = splitTerms(document.getElementById("extra-terms").value);
  const otherTerms = splitTerms(document.getElementById("other-terms").value);

  if (!displayName || !key) {
    errorEl.textContent = "Group name is required.";
    return;
  }

  const { error } = await supabaseClient.from("groups").insert({
    key,
    display_name: displayName,
    search_patterns: uniqueTerms([displayName, ...extraTerms, ...otherTerms]),
    members: extraTerms,
    is_regex: false,
  });

  if (error) {
    errorEl.textContent =
      error.code === "23505"
        ? `A group with a matching name already exists (URL key "${key}" is taken) -- pick a different name.`
        : "Failed to add group: " + error.message;
    return;
  }

  successEl.textContent = `Added "${displayName}". It'll start picking up articles on the next fetch.`;
  e.target.reset();
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

const oldestDateEl = document.getElementById("oldest-date");
const settingsStatusEl = document.getElementById("settings-status");

async function loadSettings() {
  const { data, error } = await supabaseClient
    .from("app_settings")
    .select("oldest_article_date")
    .eq("id", 1)
    .maybeSingle();
  if (error || !data) {
    settingsStatusEl.textContent = "Settings not set up yet (run supabase/007_cutoff_and_group_cleanup.sql).";
    return;
  }
  oldestDateEl.value = data.oldest_article_date;
}

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  settingsStatusEl.textContent = "Saving...";
  const { error } = await supabaseClient
    .from("app_settings")
    .update({ oldest_article_date: oldestDateEl.value })
    .eq("id", 1);
  settingsStatusEl.textContent = error ? "Save failed: " + error.message : "Saved. Applies from the next fetch.";
});

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
    .select("key, display_name, members, search_patterns, is_regex, last_refreshed_at")
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
      const membersStr = (g.members || []).join(", ");
      // Everything in search_patterns that isn't the group name or a member.
      const hidden = new Set([g.display_name, ...(g.members || [])].map((t) => plainTerm(t).toLowerCase()));
      const otherStr = (g.search_patterns || [])
        .map(plainTerm)
        .filter((t) => !hidden.has(t.toLowerCase()))
        .join(", ");
      const count = counts[i].count ?? 0;
      const lastRefreshed = g.last_refreshed_at ? relativeTime(new Date(g.last_refreshed_at)) : "never";
      return `
        <div class="manage-row" data-key="${escapeHtml(g.key)}" data-regex="${g.is_regex ? "1" : ""}" data-patterns='${escapeHtml(JSON.stringify(g.search_patterns || []))}'>
          <input type="text" class="mg-display-name" value="${escapeHtml(g.display_name)}" />
          <label class="mg-label">Members (shown beside the group name)</label>
          <input type="text" class="mg-extra-terms" value="${escapeHtml(membersStr)}" placeholder="members, comma-separated" />
          <label class="mg-label">Other search terms (not shown)</label>
          <input type="text" class="mg-other-terms" value="${escapeHtml(otherStr)}" placeholder="e.g. nicknames, other spellings" />
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
  const members = splitTerms(row.querySelector(".mg-extra-terms").value);
  const otherTerms = splitTerms(row.querySelector(".mg-other-terms").value);

  if (!displayName) {
    errorEl.textContent = "Group name can't be empty.";
    return;
  }

  // Search terms = group name + members + other terms. Existing entries
  // that are still listed keep their stored form (regex groups store
  // e.g. "\bSKZ\b"); terms removed from both boxes are dropped; new
  // terms are added (word-bounded for regex groups).
  let existingPatterns = [];
  try {
    existingPatterns = JSON.parse(row.dataset.patterns || "[]");
  } catch {
    existingPatterns = [];
  }
  const wanted = uniqueTerms([displayName, ...members, ...otherTerms]);
  const wantedLower = new Set(wanted.map((t) => t.toLowerCase()));
  const kept = uniqueTerms(existingPatterns).filter((p) => wantedLower.has(plainTerm(p).toLowerCase()));
  const keptLower = new Set(kept.map((p) => plainTerm(p).toLowerCase()));
  const isRegex = row.dataset.regex === "1";
  const added = wanted
    .filter((t) => !keptLower.has(t.toLowerCase()))
    .map((t) => (isRegex ? `\\b${escapeRegex(t)}\\b` : t));
  const mergedPatterns = [...kept, ...added];

  const { error } = await supabaseClient
    .from("groups")
    .update({ display_name: displayName, members, search_patterns: mergedPatterns })
    .eq("key", key);

  if (error) {
    errorEl.textContent = "Save failed: " + error.message;
    return;
  }
  loadManageGroups();
}

async function deleteGroup(row, key) {
  const displayName = row.querySelector(".mg-display-name").value;
  if (!confirm(`Delete "${displayName}"? This also deletes all its stored articles and article text from the database. This can't be undone.`)) return;

  const { error } = await supabaseClient.from("groups").delete().eq("key", key);
  if (error) {
    row.querySelector(".mg-error").textContent = "Delete failed: " + error.message;
    return;
  }
  loadManageGroups();
}

// ---------- Feedback ----------

async function loadFeedbackPanel() {
  const panel = document.getElementById("feedback-panel");
  const { data, error } = await supabaseClient
    .from("feedback")
    .select("id, message, status, created_at")
    .order("created_at", { ascending: false });

  if (error) {
    panel.innerHTML = `<p class="error-text">Failed to load: ${escapeHtml(error.message)}</p>`;
    return;
  }

  if (!data.length) {
    panel.innerHTML = `<p class="hint">Nothing posted yet.</p>`;
    return;
  }

  panel.innerHTML = data
    .map(
      (f) => `
        <div class="manage-row" data-id="${f.id}">
          <span class="feedback-status status-${f.status}">${f.status === "done" ? "Done" : "Open"}</span>
          <div class="feedback-text">${escapeHtml(f.message)}</div>
          <div class="hint">${relativeTime(new Date(f.created_at))}</div>
          <div class="manage-row-actions">
            <button class="fb-toggle">Mark ${f.status === "done" ? "Open" : "Done"}</button>
            <button class="fb-delete">Delete</button>
          </div>
          <p class="error-text fb-error"></p>
        </div>`,
    )
    .join("");

  panel.querySelectorAll(".manage-row").forEach((row) => {
    const id = row.dataset.id;
    const currentStatus = row.querySelector(".feedback-status").classList.contains("status-done") ? "done" : "open";
    row.querySelector(".fb-toggle").addEventListener("click", () => toggleFeedbackStatus(row, id, currentStatus));
    row.querySelector(".fb-delete").addEventListener("click", () => deleteFeedback(row, id));
  });
}

async function toggleFeedbackStatus(row, id, currentStatus) {
  const nextStatus = currentStatus === "done" ? "open" : "done";
  const { error } = await supabaseClient.from("feedback").update({ status: nextStatus }).eq("id", id);
  if (error) {
    row.querySelector(".fb-error").textContent = "Update failed: " + error.message;
    return;
  }
  loadFeedbackPanel();
}

async function deleteFeedback(row, id) {
  if (!confirm("Delete this entry? This can't be undone.")) return;
  const { error } = await supabaseClient.from("feedback").delete().eq("id", id);
  if (error) {
    row.querySelector(".fb-error").textContent = "Delete failed: " + error.message;
    return;
  }
  loadFeedbackPanel();
}
