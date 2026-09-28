export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public requestId?: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
  csrf?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      "Could not reach FlowPilot. Check your connection and try again.",
      0,
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      path !== "/auth/me"
    )
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(
      body?.error?.message ?? "The request could not be completed. Try again.",
      response.status,
      response.headers.get("X-Request-ID") ?? undefined,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Try again.";
}
