import { hasServerAiKey } from "../server/ai";
import { handle, json } from "../server/http";
import { requestKeys } from "../server/keys";

export const GET = handle(async () => {
  const sent = requestKeys();
  return json(
    { tmdb: !!(sent.tmdb || process.env.TMDB_API_KEY?.trim()), ai: !!(sent.ai || hasServerAiKey()) },
    200,
    { "cache-control": "no-store" },
  );
});
