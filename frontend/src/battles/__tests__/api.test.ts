import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { fetchBattleDetail, fetchBattlesForScene } from '../api';

describe('battles api (#5290)', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
  });

  it('Regression for #5290: the battle reads send the character the tab plays', async () => {
    await fetchBattleDetail(7, 42);
    await fetchBattlesForScene(3, 42);
    expect(apiFetch.mock.calls[0][0]).toBe('/api/battles/7/');
    expect(apiFetch.mock.calls[0][1]).toEqual({ headers: { 'X-Character-ID': '42' } });
    expect(apiFetch.mock.calls[1][0]).toBe('/api/battles/?scene=3');
    expect(apiFetch.mock.calls[1][1]).toEqual({ headers: { 'X-Character-ID': '42' } });
  });

  it('Regression for #5290: no active character sends no header', async () => {
    await fetchBattleDetail(7, null);
    expect(apiFetch.mock.calls[0][1]).toEqual({ headers: {} });
  });
});
