import { config } from "../config";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  // The anon key is public: the database enforces read-only access, not the key.
  if (config.anonKey) {
    h.apikey = config.anonKey;
    h.Authorization = `Bearer ${config.anonKey}`;
  }
  return h;
}

/** GET from the Supabase-style REST API. Throws ApiError with a human-readable message. */
export async function rest<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(config.restUrl + path, { headers: headers(), signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "Could not reach the data service. Check your connection and try again.");
  }
  if (!res.ok) {
    let detail = "";
    try {
      detail = ((await res.json()) as { message?: string }).message ?? "";
    } catch {
      /* the body was not JSON; the status is enough */
    }
    throw new ApiError(res.status, `The data service answered ${res.status}${detail ? `: ${detail}` : ""}.`);
  }
  return (await res.json()) as T;
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}
