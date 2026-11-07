export function attemptDeadline(attempt: { expires_at?: string; started_at: string }, durationMinutes: number) {
  if (attempt.expires_at) return Date.parse(attempt.expires_at);
  return Date.parse(attempt.started_at) + durationMinutes * 60_000;
}

export function remainingSeconds(deadlineMs: number, nowMs = Date.now()) {
  if (!Number.isFinite(deadlineMs)) return 0;
  return Math.max(0, Math.ceil((deadlineMs - nowMs) / 1000));
}
