async function loadGroups() {
  const grid = document.getElementById("group-grid");
  const { data, error } = await supabaseClient
    .from("groups")
    .select("key, display_name")
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
    .map(
      (g) =>
        `<a class="group-btn" href="group.html?g=${encodeURIComponent(g.key)}">${escapeHtml(g.display_name)}</a>`,
    )
    .join("");
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

loadGroups();
