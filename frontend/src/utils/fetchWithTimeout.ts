// Defensive client-side ceiling on top of a fetch call (user request --
// Tag Lab's /prepare and /run calls must never wait on "Waiting for the
// model's response…" forever, even if the root cause of an occasional hang,
// seen as a logged 200 with no UI update, turns out to be outside the
// component). Extracted out of TagLabModal.tsx (its only caller) so a
// component file doesn't have to export a non-component for its own test.
export async function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}
