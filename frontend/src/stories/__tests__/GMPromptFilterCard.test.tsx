/**
 * Tests for GMPromptFilterCard (#4101, demo Screen 5). Mocks the low-level
 * `apiFetch` seam (never the exported query hooks) so the real
 * `useGMPromptFilters`/`useSetGMPromptFilter` hooks are exercised — see
 * `GMPromptRow.test.tsx` for the established idiom this mirrors.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const mockApiFetch = vi.fn();

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...(args as [])),
}));

import { GMPromptFilterCard } from '../components/GMPromptFilterCard';

const rows = [
  { group: 'dramatic_moment', label: 'Dramatic Moment', enabled: true },
  { group: 'audere', label: 'Audere / Audere Majora', enabled: false },
  { group: 'miracle', label: 'Miracles', enabled: true },
  { group: 'death', label: 'Deaths', enabled: true },
  { group: 'stake_outcome', label: 'Stake outcomes', enabled: true },
];

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('GMPromptFilterCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders five Prompt me checkboxes with the right checked state, plus the fixed Player actions row', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(rows),
    } as Response);

    render(<GMPromptFilterCard />, { wrapper: createWrapper() });

    const checkboxes = await screen.findAllByRole('checkbox');
    expect(checkboxes).toHaveLength(5);

    // Each checkbox has a distinct accessible name ("Prompt me: {label}") --
    // findable by role+name, not just by DOM order.
    expect(screen.getByRole('checkbox', { name: 'Prompt me: Dramatic Moment' })).toBeChecked();
    expect(
      screen.getByRole('checkbox', { name: 'Prompt me: Audere / Audere Majora' })
    ).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Prompt me: Miracles' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Prompt me: Deaths' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Prompt me: Stake outcomes' })).toBeChecked();

    expect(screen.getByText('Player actions')).toBeInTheDocument();
    expect(screen.getByText('Never prompt. Players write their own.')).toBeInTheDocument();
    // The fixed row carries no checkbox of its own.
    expect(screen.getAllByRole('checkbox')).toHaveLength(5);
  });

  it('clicking a row posts {group, enabled: !current} and reflects the server response', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(rows) } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve(rows.map((r) => (r.group === 'audere' ? { ...r, enabled: true } : r))),
      } as Response);

    render(<GMPromptFilterCard />, { wrapper: createWrapper() });

    const audereCheckbox = await screen.findByRole('checkbox', {
      name: 'Prompt me: Audere / Audere Majora',
    });
    await user.click(audereCheckbox); // currently disabled

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2));
    const [url, options] = mockApiFetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/gm/prompt-filters/set/');
    expect(JSON.parse(options.body as string)).toEqual({ group: 'audere', enabled: true });

    await waitFor(() => expect(audereCheckbox).toBeChecked());
  });

  it('shows the load failure in role="alert"', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({}),
    } as Response);

    render(<GMPromptFilterCard />, { wrapper: createWrapper() });

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});
