async function loadGroups() {
  const grid = document.getElementById("group-grid");
  const { data, error } = await supabaseClient
    .from("groups")
    .select("key, display_name, search_patterns")
    .order("display_name", { ascending: true });

  if (error) {
    grid.innerHTML = `<p class="hint">Failed to load groups.</p>`;
    return;
  }

  if (!data.length) {
    grid.innerHTML = `<p class="hint">No groups yet.</p>`;
    return;
  }

  grid.innerHTML = data
    .map((g) => {
      const members = (g.search_patterns || []).filter((p) => p !== g.display_name);
      const membersLine = members.length
        ? `<span class="group-btn-members">${escapeHtml(members.join(", "))}</span>`
        : "";
      return `<a class="group-btn" href="group.html?g=${encodeURIComponent(g.key)}">
        <span class="group-btn-name">${escapeHtml(g.display_name)}</span>
        ${membersLine}
      </a>`;
    })
    .join("");
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function loadFetchStatus() {
  const el = document.getElementById("fetch-status-line");
  const { data, error } = await supabaseClient.from("fetch_status").select("last_run_at, last_run_ok").eq("id", 1).maybeSingle();

  if (error || !data || !data.last_run_at) {
    el.textContent = "";
    return;
  }

  const lastRun = new Date(data.last_run_at);
  const hoursAgo = (Date.now() - lastRun.getTime()) / 3600000;
  const rel = relativeTime(lastRun);

  if (data.last_run_ok === false) {
    el.innerHTML = `<span class="error-text">Last scheduled fetch failed (${rel}) -- feeds may be stale.</span>`;
  } else if (hoursAgo > 14) {
    el.innerHTML = `<span class="error-text">No successful fetch in over 14h (last: ${rel}) -- feeds may be stale.</span>`;
  } else {
    el.textContent = `Data last updated ${rel}.`;
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

loadGroups();
loadFetchStatus();
