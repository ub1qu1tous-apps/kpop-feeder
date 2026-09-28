// Best-effort member lookup via Wikipedia's public API (free, no key,
// CORS-enabled for anonymous JS clients via origin=*). Wikitext infobox
// formatting varies page to page, so this can fail or return junk --
// callers should treat the result as a starting point to review/edit,
// not a guaranteed-correct answer.

const WIKI_API = "https://en.wikipedia.org/w/api.php?format=json&formatversion=2&origin=*";
const MAX_PAGES_TO_CHECK = 3;

async function lookupMembersFromWikipedia(groupName) {
  // Search the plain name, limited to music-artist pages: extra words
  // like "kpop group" pulled in the agency or a member's page instead,
  // and the filter finds pages titled differently from the short name
  // (e.g. "TXT" -> "Tomorrow X Together").
  let titles = await searchTitles(`${groupName} hastemplate:"Infobox musical artist"`);
  if (!titles.length) titles = await searchTitles(groupName);

  // Check the page whose title matches the name first (e.g. "KiiiKiii",
  // "Ive (group)"), then the rest in search order, until one has a
  // members list in its infobox.
  const want = normalizeTitle(groupName);
  const ordered = [
    ...titles.filter((t) => normalizeTitle(t) === want),
    ...titles.filter((t) => normalizeTitle(t) !== want),
  ];

  for (const title of ordered.slice(0, MAX_PAGES_TO_CHECK)) {
    const wtData = await (
      await fetch(`${WIKI_API}&action=query&prop=revisions&rvprop=content&rvslots=main&titles=${encodeURIComponent(title)}`)
    ).json();
    const wikitext = wtData?.query?.pages?.[0]?.revisions?.[0]?.slots?.main?.content || "";
    const members = parseInfoboxMembers(wikitext);
    if (members.length) return members;
  }
  return [];
}

async function searchTitles(query) {
  const data = await (
    await fetch(`${WIKI_API}&action=query&list=search&srlimit=5&srsearch=${encodeURIComponent(query)}`)
  ).json();
  return (data?.query?.search || []).map((s) => s.title);
}

// "Ive (group)" -> "ive", "LE SSERAFIM" -> "lesserafim"
function normalizeTitle(s) {
  return s.toLowerCase().replace(/\(.*?\)/g, "").replace(/[^a-z0-9]/g, "");
}

function parseInfoboxMembers(wikitext) {
  const match = wikitext.match(/\|\s*(?:current_members|members)\s*=\s*([\s\S]*?)(?:\n\s*\||\n\}\})/);
  if (!match) return [];

  let block = match[1];
  block = block.replace(/\{\{plainlist\|?/gi, "").replace(/\{\{hlist\|?/gi, "").replace(/\}\}/g, "");
  block = block.replace(/\[\[([^\]|]*\|)?([^\]]+)\]\]/g, "$2"); // [[Page|Name]] or [[Name]] -> Name
  block = block.replace(/<br\s*\/?>/gi, "\n");
  block = block.replace(/'''?/g, ""); // wiki bold/italic markup
  block = block.replace(/<!--[\s\S]*?-->/g, ""); // HTML comments

  const names = block
    .split(/\n|\*|,/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && s.length < 40 && !/[{}|=]/.test(s));

  return [...new Set(names)];
}
