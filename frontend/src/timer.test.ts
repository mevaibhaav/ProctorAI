import { describe, expect, it } from 'vitest';
import { attemptDeadline, remainingSeconds } from './timer';

describe('exam timer', () => {
  it('uses the server-provided UTC expiry timestamp', () => {
    const deadline = attemptDeadline({ started_at: '2026-11-07T10:00:00+00:00', expires_at: '2026-11-07T10:30:00+00:00' }, 30);
    expect(new Date(deadline).toISOString()).toBe('2026-11-07T10:30:00.000Z');
  });

  it('counts down to zero without becoming negative', () => {
    const deadline = Date.parse('2026-11-07T10:30:00Z');
    expect(remainingSeconds(deadline, deadline - 1500)).toBe(2);
    expect(remainingSeconds(deadline, deadline + 1)).toBe(0);
  });
});
