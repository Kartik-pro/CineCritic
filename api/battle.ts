import { handle } from "../server/http.js";
import { battleOperation } from "../server/operations.js";
import { streamOperation } from "../server/pipeline.js";

export const POST = handle(async (req) => streamOperation(req, "battle", battleOperation));
