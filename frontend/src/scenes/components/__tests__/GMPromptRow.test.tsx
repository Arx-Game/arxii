/**
 * Tests for GMPromptRow — one row of the GM prompt queue (#4101; was the
 * #2183 DramaticMomentSuggestionChip). Covers both NARRATED and PENDING row
 * states per controller amendment R6-2.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { GMPrompt } from '../../types';

// Mock the low-level fetch seam rather than the exported query fns — the
// mutation hooks close over the module-local apiFetch call, so re-exporting
// mocked versions from '../../gmPromptQueries' would never be reached.
const mockApiFetch = vi.fn(() =>
  Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response)
);

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...(args as [])),
}));

import { GMPromptRow } from '../GMPromptRow';

function makePrompt(overrides: Partial<GMPrompt> = {}): GMPrompt {
  return {
    id: 7,
    kind: 'crossing',
    kind_label: 'Crossing',
    status: 'pending',
    scene: 1,
    character_sheet: 3,
    subject_name: 'Rowan Ashcombe',
    subject_persona_id: 30,
    moment_type: null,
    moment_type_label: '',
    technique_name: '',
    stake_summary: '',
    room_text: 'room',
    private_text: 'vision',
    prepared_for_character: true,
    created_at: '2026-10-02T00:00:00Z',
    ...overrides,
  };
}

function makeMoment(overrides: Partial<GMPrompt> = {}): GMPrompt {
  return makePrompt({
    id: 8,
    kind: 'dramatic_moment',
    kind_label: 'Dramatic Moment',
    subject_name: 'Tamsin Vale',
    moment_type_label: 'stand against the collapse',
    ...overrides,
  });
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('GMPromptRow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response)
    );
  });

  it('renders a PENDING narration row with Open and Dismiss', () => {
    render(<GMPromptRow prompt={makePrompt()} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    // The emphasis word is its own <strong> (F4), so the full sentence is
    // asserted against the row's combined text content rather than one node.
    expect(screen.getByTestId('gm-prompt-row')).toHaveTextContent(
      'Crossing: Rowan Ashcombe. Narrate it?'
    );
    expect(screen.getByRole('button', { name: /open crossing/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /dismiss crossing/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /done crossing/i })).toBeNull();
  });

  it('renders a NARRATED row with Open and Done instead of Dismiss (R6-2)', () => {
    render(
      <GMPromptRow prompt={makePrompt({ status: 'narrated' })} sceneId="5" onOpen={vi.fn()} />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('gm-prompt-row')).toHaveTextContent(
      'Crossing: Rowan Ashcombe. Narrated.'
    );
    expect(screen.getByRole('button', { name: /open crossing/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /done crossing/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /dismiss crossing/i })).toBeNull();
  });

  it('clicking Open on a narration row calls onOpen with the prompt', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const prompt = makePrompt();
    render(<GMPromptRow prompt={prompt} sceneId="5" onOpen={onOpen} />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /open crossing/i }));
    expect(onOpen).toHaveBeenCalledWith(prompt);
  });

  it('clicking Done on a NARRATED row POSTs to the dismiss endpoint', async () => {
    const user = userEvent.setup();
    render(
      <GMPromptRow prompt={makePrompt({ status: 'narrated' })} sceneId="5" onOpen={vi.fn()} />,
      { wrapper: createWrapper() }
    );
    await user.click(screen.getByRole('button', { name: /done crossing/i }));
    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith('/api/gm/prompts/7/dismiss/', { method: 'POST' })
    );
  });

  it('clicking Dismiss on a PENDING row POSTs to the dismiss endpoint', async () => {
    const user = userEvent.setup();
    render(<GMPromptRow prompt={makePrompt()} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /dismiss crossing/i }));
    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith('/api/gm/prompts/7/dismiss/', { method: 'POST' })
    );
  });

  it('renders a dramatic-moment row with Confirm and Dismiss, no Open', () => {
    render(<GMPromptRow prompt={makeMoment()} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('gm-prompt-row')).toHaveTextContent(
      "Tamsin Vale's stand against the collapse. Confirm?"
    );
    expect(screen.getByRole('button', { name: /confirm dramatic moment/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /dismiss dramatic moment/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /open dramatic moment/i })).toBeNull();
  });

  it('clicking Confirm POSTs to the confirm endpoint with the prompt id', async () => {
    const user = userEvent.setup();
    render(<GMPromptRow prompt={makeMoment({ id: 42 })} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    await user.click(screen.getByRole('button', { name: /confirm dramatic moment/i }));
    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith('/api/gm/prompts/42/confirm/', { method: 'POST' })
    );
  });

  // Demo-fidelity fix round: F3 (ruling R14-2) -- a narration row drops the
  // separate kind-chip badge since the ruled text already carries the kind;
  // a dramatic-moment row keeps it since its own text never mentions it.
  it('drops the kind-chip badge on a narration row (F3)', () => {
    render(<GMPromptRow prompt={makePrompt()} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    // "Crossing" only appears once, folded into the ruled sentence -- no
    // separate element carries just the kind label.
    expect(screen.queryByText('Crossing')).toBeNull();
    expect(screen.getByTestId('gm-prompt-row')).toHaveTextContent(
      'Crossing: Rowan Ashcombe. Narrate it?'
    );
  });

  it('keeps the kind-chip badge on a dramatic-moment row (F3)', () => {
    render(<GMPromptRow prompt={makeMoment()} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByText('Dramatic Moment')).toBeInTheDocument();
  });

  // F4 -- the "Narrate it?" / "Confirm?" / "Narrated." emphasis word is bold,
  // and Open/Confirm are the filled primary action, Dismiss/Done secondary.
  it('bolds the row emphasis word and gives Open the filled primary style (F4)', () => {
    render(<GMPromptRow prompt={makePrompt()} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByText('Narrate it?').tagName).toBe('STRONG');
    expect(screen.getByRole('button', { name: /open crossing/i }).className).toContain(
      'bg-primary'
    );
    expect(screen.getByRole('button', { name: /dismiss crossing/i }).className).toContain(
      'bg-secondary'
    );
  });

  it('bolds "Confirm?" and gives Confirm the filled primary style, Dismiss secondary (F4)', () => {
    render(<GMPromptRow prompt={makeMoment()} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByText('Confirm?').tagName).toBe('STRONG');
    expect(screen.getByRole('button', { name: /confirm dramatic moment/i }).className).toContain(
      'bg-primary'
    );
    expect(screen.getByRole('button', { name: /dismiss dramatic moment/i }).className).toContain(
      'bg-secondary'
    );
  });

  it('bolds "Narrated." and gives Done the secondary style (F4)', () => {
    render(
      <GMPromptRow prompt={makePrompt({ status: 'narrated' })} sceneId="5" onOpen={vi.fn()} />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByText('Narrated.').tagName).toBe('STRONG');
    expect(screen.getByRole('button', { name: /done crossing/i }).className).toContain(
      'bg-secondary'
    );
  });

  it('gives the row its rounded pill container (F4)', () => {
    render(<GMPromptRow prompt={makePrompt()} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('gm-prompt-row').className).toContain('rounded-full');
  });

  it('invalidates the gm-prompts and scene-interactions caches on successful dismiss', async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    render(
      <QueryClientProvider client={queryClient}>
        <GMPromptRow prompt={makePrompt({ id: 42 })} sceneId="5" onOpen={vi.fn()} />
      </QueryClientProvider>
    );

    await user.click(screen.getByRole('button', { name: /dismiss crossing/i }));

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['gm-prompts', '5'] })
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['scene-interactions', '5'] });
  });
});
