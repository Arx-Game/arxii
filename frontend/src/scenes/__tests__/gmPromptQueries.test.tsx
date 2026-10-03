/**
 * gmPromptQueries cache wiring (#4101 final review, F5): a narration is a new
 * feed row as well as a queue change, so a successful narrate refetches both.
 * Only the fetch seam is mocked, so the real hook runs.
 */
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const mockApiFetch = vi.fn(() =>
  Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 7 }) } as Response)
);

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...(args as [])),
}));

import { useNarrateGMPrompt } from '../gmPromptQueries';

describe('useNarrateGMPrompt', () => {
  it('refetches the queue and the scene feed after a narration lands', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useNarrateGMPrompt('5'), { wrapper });

    await result.current.mutateAsync({ promptId: 7, text: 'The floor groans.', audience: 'room' });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['scene-interactions', '5'] })
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['gm-prompts', '5'] });
  });
});
