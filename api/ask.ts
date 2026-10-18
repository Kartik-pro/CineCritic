import { handle, json, readBody, readOptions, cleanText, HttpError } from "../server/http.js";
import { generateText } from "../server/ai.js";
import { askSystem } from "../server/prompts.js";
import { stripSpoilers } from "../server/spoilers.js";
import { filmContext, isAnalysis } from "../server/context.js";
import type { ChatMessage } from "../shared/types.js";

const HISTORY_LIMIT = 8;

function readHistory(value: unknown): ChatMessage[] {
  const items = (Array.isArray(value) ? value : [])
    .filter((m): m is ChatMessage => (m?.role === "user" || m?.role === "assistant") && typeof m.content === "string")
    .slice(-HISTORY_LIMIT)
    .map((m) => ({ role: m.role, content: m.content.slice(0, 1500) }));
  while (items[0]?.role === "assistant") items.shift();
  return items;
}

export const POST = handle(async (req) => {
  const body = await readBody(req);
  const { spoiler, language } = readOptions(body);
  const question = cleanText(body.question, 800);
  if (!question) throw new HttpError(400, "Type a question first.");

  const context = isAnalysis(body.analysis) ? filmContext(body.analysis, spoiler) : "";
  const reply = await generateText({
    system: askSystem(spoiler, language, context),
    messages: [...readHistory(body.history), { role: "user", content: question }],
  });

  const answer = spoiler === "full" ? reply : stripSpoilers(reply, false).text;
  return json({ answer });
});
