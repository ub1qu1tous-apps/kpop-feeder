function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
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

const FEEDBACK_MAX = 20;

function setFormFull(isFull) {
  document.getElementById("feedback-full-notice").hidden = !isFull;
  document.getElementById("feedback-message").disabled = isFull;
  document.querySelector("#feedback-form button[type=submit]").disabled = isFull;
}

async function loadFeedback() {
  const list = document.getElementById("feedback-list");
  const { data, error } = await supabaseClient
    .from("feedback")
    .select("id, message, status, created_at")
    .order("created_at", { ascending: false });

  if (error) {
    list.innerHTML = `<li class="error-text">Failed to load: ${escapeHtml(error.message)}</li>`;
    return;
  }

  setFormFull(data.length >= FEEDBACK_MAX);

  if (!data.length) {
    list.innerHTML = `<li class="empty">Nothing posted yet -- be the first.</li>`;
    return;
  }

  list.innerHTML = data
    .map(
      (f) => `
        <li class="feedback-entry">
          <span class="feedback-status status-${f.status}">${f.status === "done" ? "Done" : "Open"}</span>
          <div class="feedback-text">${escapeHtml(f.message)}</div>
          <div class="feedback-meta">${relativeTime(new Date(f.created_at))}</div>
        </li>`,
    )
    .join("");
}

document.getElementById("feedback-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("feedback-error");
  const textarea = document.getElementById("feedback-message");
  const submitBtn = e.target.querySelector("button[type=submit]");
  errorEl.textContent = "";

  const message = textarea.value.trim();
  if (!message) {
    errorEl.textContent = "Write something first.";
    return;
  }

  submitBtn.disabled = true;
  const { error } = await supabaseClient.from("feedback").insert({ message });
  submitBtn.disabled = false;

  if (error) {
    // The DB itself refuses inserts once at 20 (in case two people post
    // at once) -- show the same friendly message as the pre-emptive check.
    errorEl.textContent = error.message.includes("Feedback board is full")
      ? ""
      : "Failed to post: " + error.message;
    loadFeedback();
    return;
  }

  textarea.value = "";
  loadFeedback();
});

loadFeedback();
