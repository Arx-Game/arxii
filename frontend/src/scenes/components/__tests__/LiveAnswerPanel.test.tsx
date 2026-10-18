/**
 * LiveAnswerPanel (#4333 slice 5, walkthrough D): the scene GM's answer panel.
 * Text is labelled placeholders; answers are staff-authored.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import type { LivePrompt } from '../../liveAnswerApi';
import type { GMPrompt } from '../../types';

const mockApiFetch = vi.fn();

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...(args as [])),
}));

import { GMPromptRow } from '../GMPromptRow';
import { LiveAnswerPanel } from '../LiveAnswerPanel';

function makePanel(overrides: Partial<LivePrompt> = {}): LivePrompt {
  return {
    id: 41,
    being_name: 'Ombrin',
    rite_name: '[placeholder rite name]',
    subject_name: 'Orla Cobbe',
    outcome_tier_name: 'Partial Success',
    answers: [
      {
        id: 11,
        outcome_tier_name: 'Partial Success',
        delay_text: '[staff-authored delay text]',
        answer_text: '[staff-authored answer text]',
        onlooker_line: '[staff-authored onlooker line]',
        used_count: 1,
      },
      {
        id: 12,
        outcome_tier_name: 'Failure',
        delay_text: '',
        answer_text: '[staff-authored failure text]',
        onlooker_line: '',
        used_count: 2,
      },
    ],
    miracles: [
      {
        id: 21,
        name: '[miracle name]',
        favor_threshold: 50,
        resonance_pool_cost: 100,
        reason: "Favor with Ombrin (4) is below this miracle's threshold (50).",
      },
    ],
    may_adapt: false,
    limit_reason: '',
    ...overrides,
  };
}

function respondWith(panel: LivePrompt) {
  mockApiFetch.mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ detail: 'Sent as a vision from Ombrin.' }),
      } as Response);
    }
    expect(url).toBe('/api/worship/live-answers/41/');
    return Promise.resolve({ ok: true, json: () => Promise.resolve(panel) } as Response);
  });
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </MemoryRouter>
    );
  };
}

function postedBody(url: string): Record<string, unknown> {
  const call = mockApiFetch.mock.calls.find(
    (c) => c[0] === url && (c[1] as RequestInit | undefined)?.method === 'POST'
  );
  return JSON.parse((call?.[1] as RequestInit).body as string) as Record<string, unknown>;
}

describe('LiveAnswerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists the answers at the roll with their use, and greys an ineligible miracle', async () => {
    respondWith(makePanel());
    render(<LiveAnswerPanel promptId={41} sceneId="5" onDone={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    expect(await screen.findByText('[staff-authored answer text]')).toBeInTheDocument();
    expect(screen.getByText('used 1 time')).toBeInTheDocument();
    expect(screen.getByText('used 2 times')).toBeInTheDocument();
    expect(screen.getByText(/onlooker_line: \[staff-authored onlooker line\]/)).toBeInTheDocument();
    expect(screen.getByText(/Showing Ombrin's answers at Partial Success and below/)).toBeVisible();
    expect(screen.getByText(/a closing rite never raises this prompt/)).toBeVisible();
    expect(screen.getByRole('radio', { name: /Miracle: \[miracle name\]/ })).toBeDisabled();
    expect(screen.getByText(/Shown greyed: Favor with Ombrin \(4\) is below/)).toBeVisible();
    // No edit control for a level that may not adapt answers.
    expect(screen.queryByRole('button', { name: 'Edit the text' })).toBeNull();
  });

  it('sends the chosen answer unchanged', async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    respondWith(makePanel());
    render(<LiveAnswerPanel promptId={41} sceneId="5" onDone={onDone} />, {
      wrapper: createWrapper(),
    });
    await screen.findByText('[staff-authored answer text]');

    await user.click(screen.getByRole('radio', { name: /Failure/ }));
    await user.click(screen.getByRole('button', { name: 'Send this answer' }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(postedBody('/api/worship/live-answers/41/answer/')).toEqual({ answer: 12, text: '' });
  });

  it('offers the edit control to a level that may adapt answers, and sends the edit', async () => {
    const user = userEvent.setup();
    respondWith(makePanel({ may_adapt: true }));
    render(<LiveAnswerPanel promptId={41} sceneId="5" onDone={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    await screen.findByText('[staff-authored answer text]');

    await user.click(screen.getByRole('button', { name: 'Edit the text' }));
    const box = screen.getByLabelText("Edit the answer's text");
    await user.clear(box);
    await user.type(box, 'GM edited answer text');
    await user.click(screen.getByRole('button', { name: 'Send this answer' }));

    await waitFor(() =>
      expect(postedBody('/api/worship/live-answers/41/answer/')).toEqual({
        answer: 11,
        text: 'GM edited answer text',
      })
    );
  });

  it('sends an eligible miracle', async () => {
    const user = userEvent.setup();
    respondWith(
      makePanel({
        miracles: [
          {
            id: 22,
            name: '[miracle name]',
            favor_threshold: 1,
            resonance_pool_cost: 10,
            reason: '',
          },
        ],
      })
    );
    render(<LiveAnswerPanel promptId={41} sceneId="5" onDone={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    await screen.findByText('[staff-authored answer text]');

    await user.click(screen.getByRole('radio', { name: /Miracle: \[miracle name\]/ }));
    await user.click(screen.getByRole('button', { name: 'Perform this miracle' }));

    await waitFor(() =>
      expect(postedBody('/api/worship/live-answers/41/answer/')).toEqual({ miracle: 22 })
    );
  });

  it('send nothing dismisses', async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    respondWith(makePanel());
    render(<LiveAnswerPanel promptId={41} sceneId="5" onDone={onDone} />, {
      wrapper: createWrapper(),
    });
    await screen.findByText('[staff-authored answer text]');

    await user.click(screen.getByRole('button', { name: 'Send nothing' }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/worship/live-answers/41/dismiss/',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('shows the limit and sends nothing when the being already answered this week', async () => {
    respondWith(
      makePanel({ limit_reason: 'Ombrin has already answered Orla live this game week.' })
    );
    render(<LiveAnswerPanel promptId={41} sceneId="5" onDone={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    expect(
      await screen.findByText(/Ombrin has already answered Orla live this game week/)
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Send this answer' })).toBeDisabled();
  });
});

describe('a live being answer row', () => {
  it('opens the panel in the queue', async () => {
    const user = userEvent.setup();
    respondWith(makePanel());
    const prompt = {
      id: 41,
      kind: 'being_answer',
      kind_label: 'Being answer',
      status: 'pending',
      scene: 5,
      character_sheet: 3,
      subject_name: 'Orla Cobbe',
      subject_persona_id: 30,
      moment_type: null,
      moment_type_label: '',
      technique_name: '',
      stake_summary: '',
      being_answer_summary: "Orla Cobbe's [placeholder rite name] to Ombrin (Partial Success).",
      being_answer_table: null,
      being_answer_live: true,
      room_text: '',
      private_text: '',
      prepared_for_character: false,
      created_at: '2026-10-18T00:00:00Z',
    } as GMPrompt;
    render(<GMPromptRow prompt={prompt} sceneId="5" onOpen={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('gm-prompt-row')).toHaveTextContent(
      "Orla Cobbe's [placeholder rite name] to Ombrin (Partial Success)."
    );
    await user.click(screen.getByRole('button', { name: 'Open' }));
    expect(await screen.findByText('[staff-authored answer text]')).toBeInTheDocument();
  });
});
