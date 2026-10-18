import { handle, json, readBody, readOptions, HttpError } from "../server/http.js";
import { generateText } from "../server/ai.js";
import { compareSystem } from "../server/prompts.js";
import { stripSpoilers } from "../server/spoilers.js";
import { comparisonContext, isAnalysis } from "../server/context.js";
import { compareScores, dimensionScores } from "../shared/scoring.js";

export const POST = handle(async (req) => {
  const body = await readBody(req);
  const { spoiler, language } = readOptions(body);
  const { a, b } = body;
  if (!isAnalysis(a) || !isAnalysis(b)) throw new HttpError(400, "Two analyses are required.");

  const comparison = compareScores(dimensionScores(a.critique), dimensionScores(b.critique));
  const reply = await generateText({
    system: compareSystem(spoiler, language),
    messages: [{ role: "user", content: comparisonContext(a, b, comparison) }],
  });

  const narrative = spoiler === "full" ? reply : stripSpoilers(reply, false).text;
  return json({ narrative });
});
