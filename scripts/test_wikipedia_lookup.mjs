// Diagnostic only: runs the admin page's "Look up members (Wikipedia)"
// function (js/wikipedia.js, unchanged) for a list of groups.
import fs from "node:fs";

const realFetch = globalThis.fetch;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Wikipedia rate-limits shared CI IPs; space requests out and retry.
globalThis.fetch = async (url, opts = {}) => {
  for (let attempt = 0; ; attempt++) {
    await sleep(1500);
    const resp = await realFetch(url, {
      ...opts,
      headers: { "User-Agent": "kpop-feeder-diagnostic/1.0 (github actions)", ...(opts.headers || {}) },
    });
    const text = await resp.text();
    if (text.startsWith("{") || attempt >= 3) return new Response(text, { status: resp.status });
    console.log(`  (rate limited, retrying in ${5 * (attempt + 1)}s)`);
    await sleep(5000 * (attempt + 1));
  }
};

eval(fs.readFileSync("js/wikipedia.js", "utf8") + "\nglobalThis.lookupMembersFromWikipedia = lookupMembersFromWikipedia;");

const names = (process.env.NAMES || "KiiiKiii").split(",").map((s) => s.trim()).filter(Boolean);
for (const name of names) {
  try {
    const members = await lookupMembersFromWikipedia(name);
    console.log(`${name}: ${members.length ? members.join(", ") : "NOT FOUND"}`);
  } catch (e) {
    console.log(`${name}: ERROR ${e.message}`);
  }
}
