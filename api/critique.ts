import { handle, json, readBody, readOptions, cleanText, HttpError } from "../server/http";
import { findMovie, getDetails, getSimilar } from "../server/tmdb";
import { runCritique } from "../server/critique";
import type { CritiqueResponse, Movie } from "../shared/types";

export const POST = handle(async (req) => {
  const body = await readBody(req);
  const { spoiler, language } = readOptions(body);

  let id = Number.isInteger(body.id) && (body.id as number) > 0 ? (body.id as number) : 0;
  let alternatives: Movie[] = [];

  if (!id) {
    const query = cleanText(body.query, 120);
    if (!query) throw new HttpError(400, "Enter a film name first.");
    const found = await findMovie(query);
    if (!found) throw new HttpError(404, `No film matched “${query}”. Check the spelling or add the year, like “Heat (1995)”.`);
    id = found.best.id;
    alternatives = found.alternatives;
  }

  const [movie, similar] = await Promise.all([getDetails(id), getSimilar(id).catch(() => [])]);
  const { critique, removed } = await runCritique(movie, spoiler, language);

  const notices = removed ? [`${removed} sentence(s) were removed by the spoiler filter to keep this analysis safe.`] : [];
  const response: CritiqueResponse = {
    analysis: { movie, critique, similar, spoiler, language, notices, createdAt: Date.now() },
    alternatives,
  };
  return json(response);
});
