(async function guard() {
  const { data } = await supabaseClient.auth.getSession();
  if (!data.session) location.href = "login.html";
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
});
