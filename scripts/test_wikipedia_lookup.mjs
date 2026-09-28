// Diagnostic only: shows what the admin page's "Look up members
// (Wikipedia)" button sees for a few groups, to debug misses.
import fs from "node:fs";

const realFetch = globalThis.fetch;
globalThis.fetch = (url, opts = {}) =>
  realFetch(url, { ...opts, headers: { "User-Agent": "kpop-feeder-diagnostic/1.0 (github actions)", ...(opts.headers || {}) } });

// Load the same lookup function the admin page uses.
eval(fs.readFileSync("js/wikipedia.js", "utf8") + "\nglobalThis.lookupMembersFromWikipedia = lookupMembersFromWikipedia;");

const api = "https://en.wikipedia.org/w/api.php?format=json&origin=*";
const names = (process.env.NAMES || "KiiiKiii,aespa,ILLIT,Hearts2Hearts").split(",");

for (const name of names) {
  console.log(`\n==================== ${name}`);
  for (const q of [`${name} kpop group`, name]) {
    const r = await (await fetch(`${api}&action=query&list=search&srlimit=5&srsearch=${encodeURIComponent(q)}`)).json();
    console.log(`search "${q}": ` + (r?.query?.search || []).map((s) => s.title).join(" | "));
  }
  const top = (await (await fetch(`${api}&action=query&list=search&srlimit=1&srsearch=${encodeURIComponent(name)}`)).json())?.query?.search?.[0]?.title;
  if (top) {
    const wt = (await (await fetch(`${api}&action=query&prop=revisions&rvprop=content&rvslots=main&formatversion=2&titles=${encodeURIComponent(top)}`)).json())
      ?.query?.pages?.[0]?.revisions?.[0]?.slots?.main?.content || "";
    console.log(`page "${top}": ${wt.length} chars`);
    const infobox = wt.match(/\|\s*(?:current_members|members|past_members)\s*=[^\n]*(\n[^|}][^\n]*)*/g);
    console.log("infobox member fields:", JSON.stringify(infobox));
    const sec = wt.match(/==+\s*Members\s*==+[\s\S]{0,800}/i);
    console.log("Members section:", sec ? JSON.stringify(sec[0]) : "none");
  }
  console.log("lookupMembersFromWikipedia ->", JSON.stringify(await lookupMembersFromWikipedia(name)));
}
