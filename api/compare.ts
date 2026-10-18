import { handle, json, readBody, readOptions, HttpError } from "../server/http";
import { generateText } from "../server/ai";
import { compareSystem } from "../server/prompts";
import { stripSpoilers } from "../server/spoilers";
import { comparisonContext, isAnalysis } from "../server/context";
import { compareScores, dimensionScores } from "../shared/scoring";

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
