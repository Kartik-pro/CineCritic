import { handle } from "../server/http.js";
import { connectionOperation } from "../server/operations.js";
import { streamOperation } from "../server/pipeline.js";

export const POST = handle(async (req) => streamOperation(req, "connection", connectionOperation));
