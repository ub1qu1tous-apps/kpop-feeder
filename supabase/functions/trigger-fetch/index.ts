// Holds the GitHub token so it never reaches the browser. Two modes:
//   { group_key: "..." } -- public (no login required), one group,
//     cooldown tracked per-group in groups.last_refreshed_at.
//   { all: true } -- admin-only (must send the logged-in admin's own
//     session token, not the anon key), fetches every group, cooldown
//     tracked in fetch_status.last_run_at.
// Either way: dispatches the "Fetch articles" workflow, polls it to
// completion (or a timeout), and reports back so the frontend knows
// when to re-query Supabase.

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

// The gateway already verified this JWT's signature before invoking us
// (verify_jwt is on by default) -- we just need to read its role claim
// to tell "anon key" apart from "a real logged-in admin session".
function jwtRole(req: Request): string | null {
  const auth = req.headers.get("Authorization") || "";
  const token = auth.replace(/^Bearer\s+/i, "");
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    let b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const payload = JSON.parse(atob(b64));
    return payload.role ?? null;
  } catch {
    return null;
  }
}

async function dispatchAndPoll(inputs: Record<string, string>) {
  const triggeredAt = new Date();

  const dispatchResp = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: "POST",
      headers: { ...githubHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main", inputs }),
    },
  );
  if (dispatchResp.status !== 204) {
    const detail = await dispatchResp.text();
    return json({ error: "failed to trigger workflow", detail }, 502);
  }

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
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });
  if (req.method !== "POST") return json({ error: "method not allowed" }, 405);

  let body: { group_key?: string; all?: boolean };
  try {
    body = await req.json();
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }

  if (body.all === true) {
    if (jwtRole(req) !== "authenticated") {
      return json({ error: "admin login required" }, 401);
    }

    const statusResp = await supabaseRest(`fetch_status?id=eq.1&select=last_run_at`);
    const statusRows = await statusResp.json();
    const lastRunAt = statusRows[0]?.last_run_at;

    if (lastRunAt) {
      const elapsed = Date.now() - new Date(lastRunAt).getTime();
      if (elapsed < COOLDOWN_MS) {
        const retryAfterSeconds = Math.ceil((COOLDOWN_MS - elapsed) / 1000);
        return json({ error: "cooldown", retry_after_seconds: retryAfterSeconds }, 429);
      }
    }

    await supabaseRest(`fetch_status?id=eq.1`, {
      method: "PATCH",
      body: JSON.stringify({ last_run_at: new Date().toISOString() }),
    });

    return dispatchAndPoll({});
  }

  const groupKey = String(body.group_key ?? "").trim();
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
  await supabaseRest(`groups?key=eq.${encodeURIComponent(groupKey)}`, {
    method: "PATCH",
    body: JSON.stringify({ last_refreshed_at: new Date().toISOString() }),
  });

  return dispatchAndPoll({ group_key: groupKey });
});
