import { LANGUAGES, type SpoilerLevel } from "../shared/types.js";
import { AppError, HttpError, redact } from "./errors.js";
import { readKeys, requestKeys, withKeys } from "./keys.js";
import { effectiveLevel } from "./spoilers.js";

export { HttpError };

export function json(data: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return Response.json(data, { status, headers });
}

export function handle(fn: (req: Request) => Promise<Response>) {
  return async (req: Request): Promise<Response> => {
    const keys = readKeys(req);
    try {
      return await withKeys(keys, () => fn(req));
    } catch (error) {
      const secrets = [keys.tmdb, keys.ai].filter(Boolean);
      if (error instanceof AppError) {
        return json({ error: redact(error.message, secrets), code: error.code, nextStep: error.nextStep }, error.status);
      }
      if (error instanceof HttpError) return json({ error: redact(error.message, secrets) }, error.status);
      console.error(redact(error instanceof Error ? (error.stack ?? error.message) : String(error), secrets));
      return json({ error: "Something went wrong. Please try again." }, 500);
    }
  };
}

export async function readJson(req: Request): Promise<Record<string, unknown> | null> {
  try {
    const body: unknown = await req.json();
    return body && typeof body === "object" && !Array.isArray(body) ? (body as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

export async function readBody(req: Request): Promise<Record<string, unknown>> {
  const body = await readJson(req);
  if (!body) throw new HttpError(400, "Invalid request body.");
  return body;
}

export function cleanText(value: unknown, max: number): string {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim().slice(0, max) : "";
}

export function readOptions(body: Record<string, unknown>): { spoiler: SpoilerLevel; language: string } {
  const language = LANGUAGES.find((l) => l === body.language) ?? "English";
  return { spoiler: effectiveLevel(body.spoiler), language };
}

export { requestKeys };
