// Public endpoint (no login required -- the refresh button works for
// anonymous visitors too). Abuse protection is the per-group cooldown
// enforced here server-side, not authentication.
//
// Holds the GitHub token so it never reaches the browser. Triggers the
// "Fetch articles" workflow for one group, polls it to completion (or
// a timeout), and reports back so the frontend can re-query Supabase.

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const GH_PAT = Deno.env.get("GH_PAT")!;

const OWNER = "ub1qu1tous-apps";
const REPO = "kpop-feeder";
const WORKFLOW_FILE = "fetch-articles.yml";

const COOLDOWN_MS = 10 * 60 * 1000; // 10 minutes
const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 55000;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

async function supabaseRest(path: string, init: RequestInit = {}) {
  return fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
}

function githubHeaders() {
  return {
    Authorization: `Bearer ${GH_PAT}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "kpop-feeder-trigger-fetch",
  };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });
  if (req.method !== "POST") return json({ error: "method not allowed" }, 405);

  let groupKey: string;
  try {
    const body = await req.json();
    groupKey = String(body.group_key ?? "").trim();
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }
  if (!groupKey) return json({ error: "group_key is required" }, 400);

  const groupResp = await supabaseRest(
    `groups?key=eq.${encodeURIComponent(groupKey)}&select=key,last_refreshed_at`,
  );
  const groupRows = await groupResp.json();
  if (!groupResp.ok || groupRows.length === 0) {
    return json({ error: "unknown group" }, 404);
  }
  const group = groupRows[0];

  if (group.last_refreshed_at) {
    const elapsed = Date.now() - new Date(group.last_refreshed_at).getTime();
    if (elapsed < COOLDOWN_MS) {
      const retryAfterSeconds = Math.ceil((COOLDOWN_MS - elapsed) / 1000);
      return json({ error: "cooldown", retry_after_seconds: retryAfterSeconds }, 429);
    }
  }

  // Set the cooldown immediately (before dispatching/polling) so two
  // rapid clicks can't both slip through the check above.
  const triggeredAt = new Date();
  await supabaseRest(`groups?key=eq.${encodeURIComponent(groupKey)}`, {
    method: "PATCH",
    body: JSON.stringify({ last_refreshed_at: triggeredAt.toISOString() }),
  });

  const dispatchResp = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: "POST",
      headers: { ...githubHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main", inputs: { group_key: groupKey } }),
    },
  );
  if (dispatchResp.status !== 204) {
    const detail = await dispatchResp.text();
    return json({ error: "failed to trigger workflow", detail }, 502);
  }

  // Find the run we just created (the newest workflow_dispatch run on
  // main created at/after triggeredAt) and poll it to completion.
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let runUrl: string | null = null;

  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));

    const runsResp = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW_FILE}/runs` +
        `?event=workflow_dispatch&branch=main&per_page=5`,
      { headers: githubHeaders() },
    );
    if (!runsResp.ok) continue;
    const runsData = await runsResp.json();
    const run = (runsData.workflow_runs ?? []).find(
      (r: { created_at: string }) => new Date(r.created_at).getTime() >= triggeredAt.getTime() - 5000,
    );
    if (!run) continue;

    runUrl = run.html_url;
    if (run.status === "completed") {
      return json({ status: "completed", conclusion: run.conclusion, run_url: run.html_url });
    }
  }

  return json({ status: "timeout", run_url: runUrl });
});
