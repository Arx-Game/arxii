/**
 * Tests for the Beings tab (#4333 slice 4): the table GM reads a stewarded being's
 * card, answers a closed pledge from the panel, and writes a pledge type.
 * Text is labelled placeholders.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GMTable, StewardedBeing, StewardPrompt } from '../types';

const send = vi.fn();
const dismiss = vi.fn();
const savePledge = vi.fn();
const idle = { isPending: false, error: null, data: undefined };

vi.mock('../beingsQueries', () => ({
  useStewardedBeings: vi.fn(),
  useStewardPrompts: vi.fn(),
  useStewardAnswers: vi.fn(() => ({ data: { results: [] } })),
  useSendStewardAnswer: vi.fn(() => ({ ...idle, mutate: send })),
  useDismissStewardPrompt: vi.fn(() => ({ ...idle, mutate: dismiss })),
  useSavePledge: vi.fn(() => ({ ...idle, mutate: savePledge })),
  useSaveAnswer: vi.fn(() => ({ ...idle, mutate: vi.fn() })),
  useSaveSacrificeLine: vi.fn(() => ({ ...idle, mutate: vi.fn() })),
}));

import { useStewardedBeings, useStewardPrompts } from '../beingsQueries';
import { TableBeings } from '../components/TableBeings';
import { timeLeft } from '../stewardTime';

const table: GMTable = {
  id: 1,
  gm: 10,
  gm_username: 'gmUser',
  name: 'The Whitlow table',
  description: '',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  archived_at: null,
  member_count: 4,
  story_count: 0,
  viewer_role: 'gm',
};

const tiers = [
  { id: 5, name: 'Critical Success', success_level: 2 },
  { id: 4, name: 'Success', success_level: 1 },
  { id: 3, name: 'Partial Success', success_level: 0 },
  { id: 2, name: 'Failure', success_level: -1 },
  { id: 1, name: 'Critical Failure', success_level: -2 },
];

const wisket: StewardedBeing = {
  id: 9,
  name: 'Wisket',
  description: '[GM-authored being description]',
  table: 1,
  favored_resonances: ['[favored resonance]'],
  associated_resonances: [],
  favored_facets: [{ id: 70, name: 'Wolf' }],
  closing_rites: [{ id: 80, name: "Wisket's rite" }],
  pledges: [
    {
      id: 60,
      being: 9,
      name: '[GM-authored pledge name]',
      description: '[GM-authored pledge description]',
      favor_target: 10,
      span_weeks: 1,
      closing_rite: 80,
      is_active: true,
      covered_tiers: [1, 2, 3, 4],
    },
  ],
  general_covered_tiers: [],
  outcome_tiers: tiers,
  catalogue_clues: [{ id: 90, name: '[mission clue name]', target_kind: 'mission' }],
  cost_pools: [],
};

const prompt: StewardPrompt = {
  id: 33,
  being: 9,
  being_name: 'Wisket',
  table: 1,
  subject_name: 'Tobiah Fenwright',
  pledge_name: '[GM-authored pledge name]',
  outcome_tier_name: 'Success',
  sacrificed: ['[item]'],
  prayer_text: '[player-written prayer]',
  options: [
    {
      id: 41,
      outcome_tier_name: 'Success',
      pledge_name: '',
      answer_text: '[GM-authored answer text]',
      delay_text: '[GM-authored delay text]',
    },
  ],
  may_write_free_text: true,
  catalogue_clues: [{ id: 90, name: '[mission clue name]', target_kind: 'mission' }],
  window_ends_at: new Date(Date.now() + (2 * 24 + 21) * 3_600_000 + 60_000).toISOString(),
};

function mockData(prompts: StewardPrompt[]) {
  vi.mocked(useStewardedBeings).mockReturnValue({
    data: { count: 1, next: null, previous: null, results: [wisket] },
    isLoading: false,
  } as unknown as ReturnType<typeof useStewardedBeings>);
  vi.mocked(useStewardPrompts).mockReturnValue({
    data: { count: prompts.length, next: null, previous: null, results: prompts },
  } as unknown as ReturnType<typeof useStewardPrompts>);
}

describe('TableBeings', () => {
  beforeEach(() => {
    send.mockReset();
    send.mockImplementation((_vars, options) =>
      options?.onSuccess?.({ detail: 'Sent as a vision from Wisket.' })
    );
    dismiss.mockReset();
    dismiss.mockImplementation((_id, options) =>
      options?.onSuccess?.({ detail: 'Dismissed. An authored answer was drawn.' })
    );
    savePledge.mockReset();
  });

  it('shows the being card with its coverage and who may serve it', () => {
    mockData([]);
    render(<TableBeings table={table} />);

    expect(screen.getByText('Stewarded by this table')).toBeInTheDocument();
    expect(screen.getByText('favor target 10 · 1 week')).toBeInTheDocument();
    expect(
      screen.getByText(
        /4 of 5 outcome tiers written for this pledge type; Critical Success not written/
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/members of this table/)).toBeInTheDocument();
  });

  it('sends an authored answer or the steward’s own text with a clue', async () => {
    mockData([prompt]);
    const user = userEvent.setup();
    render(<TableBeings table={table} />);

    expect(screen.getByText('Wisket answers Tobiah Fenwright (Success).')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Open' }));
    const panel = screen.getByRole('region', { name: 'Wisket answers Tobiah Fenwright' });
    expect(within(panel).getByText(/2 days 21 hours left/)).toBeInTheDocument();

    await user.click(within(panel).getByRole('button', { name: 'Send as Wisket' }));
    expect(send).toHaveBeenLastCalledWith(
      { promptId: 33, body: { answer: 41, text: '' } },
      expect.anything()
    );
    // The panel closes once the prompt is answered; the confirmation stays on the tab.
    expect(screen.getByRole('status')).toHaveTextContent('Sent as a vision from Wisket.');

    await user.click(within(panel).getByLabelText(/Write free text/));
    await user.click(within(panel).getByLabelText('Your answer'));
    await user.paste('[GM-written free text]');
    await user.selectOptions(
      within(panel).getByLabelText("Attach a clue from Wisket's catalogue"),
      '90'
    );
    await user.click(within(panel).getByRole('button', { name: 'Send as Wisket' }));
    expect(send).toHaveBeenLastCalledWith(
      { promptId: 33, body: { text: '[GM-written free text]', clue: 90 } },
      expect.anything()
    );
  });

  it('dismisses a waiting answer', async () => {
    mockData([prompt]);
    const user = userEvent.setup();
    render(<TableBeings table={table} />);

    await user.click(screen.getByRole('button', { name: /Dismiss/ }));
    expect(dismiss).toHaveBeenCalledWith(33, expect.anything());
    expect(screen.getByRole('status')).toHaveTextContent(
      'Dismissed. An authored answer was drawn.'
    );
  });

  it('opens the editor with the pledge type and the coverage grid', async () => {
    mockData([]);
    const user = userEvent.setup();
    render(<TableBeings table={table} />);

    await user.click(screen.getByRole('button', { name: 'Edit Wisket' }));
    const pledgeForm = screen.getByRole('form', { name: 'Pledge type' });
    expect(within(pledgeForm).getByDisplayValue('[GM-authored pledge name]')).toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'Answer · Success' })).toBeInTheDocument();
    expect(screen.getByText('written, editing now')).toBeInTheDocument();
    expect(screen.getByText('not written')).toBeInTheDocument();
    expect(screen.getByLabelText('Sacrifice line, Wolf facet')).toBeInTheDocument();

    await user.click(within(pledgeForm).getByRole('button', { name: 'Save pledge type' }));
    expect(savePledge).toHaveBeenCalledWith(
      expect.objectContaining({
        pledgeId: 60,
        body: expect.objectContaining({ favor_target: 10, span_weeks: 1, closing_rite: 80 }),
      }),
      expect.anything()
    );
  });

  it('counts the window down in days and hours', () => {
    const now = new Date('2026-10-17T00:00:00Z');
    expect(timeLeft('2026-10-19T21:30:00Z', now)).toBe('2 days 21 hours');
    expect(timeLeft('2026-10-17T00:30:00Z', now)).toBe('under an hour');
  });
});
