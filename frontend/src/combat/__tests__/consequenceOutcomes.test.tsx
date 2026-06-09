/**
 * Tests for fetchConsequenceOutcomes (api.ts) and useConsequenceOutcomes (queries.ts).
 *
 * Uses vitest + @testing-library/react with React Query.
 * Phase 5, Task 5.1 — consequence-outcome frontend (#850).
 */

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Mock apiFetch so we never hit the network
// ---------------------------------------------------------------------------

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import * as evenniaApi from '@/evennia_replacements/api';
import { fetchConsequenceOutcomes } from '../api';
import type { ConsequenceOutcome } from '../api';
import { useConsequenceOutcomes } from '../queries';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SAMPLE_OUTCOME: ConsequenceOutcome = {
  id: 1,
  character: 42,
  check_type: 5,
  pool: 3,
  selected_consequence: 7,
  modifier_total: -2,
  summary: 'You suffer a minor wound.',
  outcome_display: [
    { label: 'Scratch', tier_name: 'Trivial', weight: 40, is_selected: false },
    { label: 'Bruised', tier_name: 'Minor', weight: 35, is_selected: true },
    { label: 'Broken arm', tier_name: 'Severe', weight: 25, is_selected: false },
  ],
  modifiers: [
    { source_kind: 'condition', source_label: 'Exhausted', value: -3 },
    { source_kind: 'equipment', source_label: 'Light armour', value: 1 },
  ],
  combat_interaction_id: 100,
  challenge_record_id: 200,
  created_at: '2026-06-01T12:00:00Z',
};

const PAGINATED_RESPONSE = { count: 1, results: [SAMPLE_OUTCOME] };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function mockApiFetch(body: unknown, ok = true) {
  const mockedApiFetch = evenniaApi.apiFetch as ReturnType<typeof vi.fn>;
  mockedApiFetch.mockResolvedValueOnce({
    ok,
    json: () => Promise.resolve(body),
  });
}

const mockedApiFetch = evenniaApi.apiFetch as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// fetchConsequenceOutcomes — plain async function
// ---------------------------------------------------------------------------

describe('fetchConsequenceOutcomes', () => {
  it('calls /api/checks/consequence-outcomes/ with no params by default', async () => {
    mockApiFetch(PAGINATED_RESPONSE);

    const results = await fetchConsequenceOutcomes();

    expect(mockedApiFetch).toHaveBeenCalledOnce();
    const [url] = mockedApiFetch.mock.calls[0] as [string];
    expect(url).toBe('/api/checks/consequence-outcomes/');
    expect(results).toHaveLength(1);
    expect(results[0].id).toBe(1);
  });

  it('appends character filter to the query string', async () => {
    mockApiFetch(PAGINATED_RESPONSE);

    await fetchConsequenceOutcomes({ character: 42 });

    const [url] = mockedApiFetch.mock.calls[0] as [string];
    expect(url).toContain('character=42');
  });

  it('appends pool filter to the query string', async () => {
    mockApiFetch(PAGINATED_RESPONSE);

    await fetchConsequenceOutcomes({ pool: 3 });

    const [url] = mockedApiFetch.mock.calls[0] as [string];
    expect(url).toContain('pool=3');
  });

  it('combines multiple filters', async () => {
    mockApiFetch(PAGINATED_RESPONSE);

    await fetchConsequenceOutcomes({ character: 42, pool: 3, page: 2 });

    const [url] = mockedApiFetch.mock.calls[0] as [string];
    expect(url).toContain('character=42');
    expect(url).toContain('pool=3');
    expect(url).toContain('page=2');
  });

  it('returns empty array when results is missing', async () => {
    mockApiFetch({ count: 0 });

    const results = await fetchConsequenceOutcomes({ character: 1 });

    expect(results).toEqual([]);
  });

  it('throws when the response is not ok', async () => {
    mockedApiFetch.mockResolvedValueOnce({ ok: false });

    await expect(fetchConsequenceOutcomes({ character: 1 })).rejects.toThrow(
      'Failed to load consequence outcomes'
    );
  });

  it('returns typed ConsequenceOutcome objects with outcome_display and modifiers', async () => {
    mockApiFetch(PAGINATED_RESPONSE);

    const results = await fetchConsequenceOutcomes({ character: 42 });

    const outcome = results[0];
    expect(outcome.outcome_display).toHaveLength(3);
    expect(outcome.modifiers).toHaveLength(2);
    expect(outcome.modifier_total).toBe(-2);
    expect(outcome.summary).toBe('You suffer a minor wound.');
  });
});

// ---------------------------------------------------------------------------
// useConsequenceOutcomes — React Query hook
// ---------------------------------------------------------------------------

function HookHarness({ characterId }: { characterId: number }) {
  const { data, isLoading, isError } = useConsequenceOutcomes({ character: characterId });

  if (isLoading) return <div data-testid="loading">loading</div>;
  if (isError) return <div data-testid="error">error</div>;

  return (
    <ul data-testid="outcome-list">
      {(data ?? []).map((o) => (
        <li key={o.id} data-testid={`outcome-${o.id}`}>
          {o.summary}
        </li>
      ))}
    </ul>
  );
}

describe('useConsequenceOutcomes', () => {
  it('renders outcomes returned by the API', async () => {
    mockApiFetch(PAGINATED_RESPONSE);

    render(<HookHarness characterId={42} />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('outcome-list')).toBeInTheDocument();
    });

    expect(screen.getByTestId('outcome-1')).toHaveTextContent('You suffer a minor wound.');
  });

  it('is disabled when no character or pool filter is given', () => {
    // No fetch should happen for empty params — hook is disabled
    render(<HookHarness characterId={0} />, { wrapper: createWrapper() });

    // Hook is disabled (characterId=0 means no character filter), stays in idle state (no loading)
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });
});
