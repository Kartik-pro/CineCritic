import { handle, json, cleanText, HttpError } from "../server/http.js";
import { isListKind, listMovies, searchMovies } from "../server/tmdb.js";

const CACHE = { "cache-control": "public, s-maxage=600, stale-while-revalidate=3600" };

export const GET = handle(async (req) => {
  const params = new URL(req.url).searchParams;
  const list = params.get("list");
  const page = Number(params.get("page")) || 1;

  if (list) {
    if (!isListKind(list)) throw new HttpError(400, "Unknown list.");
    return json(await listMovies(list, page), 200, CACHE);
  }

  const query = cleanText(params.get("q"), 120);
  if (query.length < 2) return json({ items: [] });
  return json({ items: (await searchMovies(query, "", Math.min(page, 5))).slice(0, 8) }, 200, CACHE);
});
