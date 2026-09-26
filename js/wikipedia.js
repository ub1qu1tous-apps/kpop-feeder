// Best-effort member lookup via Wikipedia's public API (free, no key,
// CORS-enabled for anonymous JS clients via origin=*). Wikitext infobox
// formatting varies page to page, so this can fail or return junk --
// callers should treat the result as a starting point to review/edit,
// not a guaranteed-correct answer.

async function lookupMembersFromWikipedia(groupName) {
  const searchUrl =
    "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&origin=*&srlimit=1" +
    `&srsearch=${encodeURIComponent(groupName + " kpop group")}`;
  const searchResp = await fetch(searchUrl);
  const searchData = await searchResp.json();
  const title = searchData?.query?.search?.[0]?.title;
  if (!title) return [];

  const wikitextUrl =
    "https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content&rvslots=main" +
    `&format=json&origin=*&formatversion=2&titles=${encodeURIComponent(title)}`;
  const wtResp = await fetch(wikitextUrl);
  const wtData = await wtResp.json();
  const wikitext = wtData?.query?.pages?.[0]?.revisions?.[0]?.slots?.main?.content || "";

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
