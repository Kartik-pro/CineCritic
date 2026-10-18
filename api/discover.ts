import { handle, json, readBody, cleanText, HttpError } from "../server/http.js";
import { generateJson } from "../server/ai.js";
import { discoverSystem } from "../server/prompts.js";
import { chooseBest, searchMovies } from "../server/tmdb.js";
import type { Pick } from "../shared/types.js";

const COUNT = 6;

export const POST = handle(async (req) => {
  const body = await readBody(req);
  const text = cleanText(body.text, 300);
  if (!text) throw new HttpError(400, "Describe a film, mood or genre first.");

  const raw = await generateJson({
    system: discoverSystem(COUNT),
    messages: [{ role: "user", content: `User input: ${text}` }],
  });
  const suggestions = (Array.isArray(raw.picks) ? raw.picks : []).slice(0, COUNT) as Record<string, unknown>[];

  const verified = await Promise.allSettled(
    suggestions.map(async (item) => {
      const title = cleanText(item.title, 120);
      const year = /^\d{4}$/.test(String(item.year)) ? String(item.year) : "";
      const found = chooseBest(await searchMovies(title, year), title, year);
      return found ? { ...found.best, why: cleanText(item.why, 140) } : null;
    }),
  );

  const seen = new Set<number>();
  const picks: Pick[] = [];
  for (const result of verified) {
    if (result.status !== "fulfilled" || !result.value || seen.has(result.value.id)) continue;
    seen.add(result.value.id);
    picks.push(result.value);
  }
  if (!picks.length) throw new HttpError(502, "No matching films were found. Try rephrasing.");
  return json({ picks });
});
