import { LANGUAGES, type SpoilerLevel } from "../shared/types";
import { effectiveLevel } from "./spoilers";

export class HttpError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function json(data: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return Response.json(data, { status, headers });
}

export function handle(fn: (req: Request) => Promise<Response>) {
  return async (req: Request): Promise<Response> => {
    try {
      return await fn(req);
    } catch (error) {
      if (error instanceof HttpError) return json({ error: error.message }, error.status);
      console.error(error);
      return json({ error: "Something went wrong. Please try again." }, 500);
    }
  };
}

export async function readBody(req: Request): Promise<Record<string, unknown>> {
  try {
    const body: unknown = await req.json();
    if (body && typeof body === "object" && !Array.isArray(body)) return body as Record<string, unknown>;
  } catch {
    throw new HttpError(400, "Invalid request body.");
  }
  throw new HttpError(400, "Invalid request body.");
}

export function cleanText(value: unknown, max: number): string {
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim().slice(0, max) : "";
}

export function readOptions(body: Record<string, unknown>): { spoiler: SpoilerLevel; language: string } {
  const language = LANGUAGES.find((l) => l === body.language) ?? "English";
  return { spoiler: effectiveLevel(body.spoiler), language };
}
