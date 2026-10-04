/**
 * StandoffCard: reading, pressing, naming terms, fighting and sharing sparks (#4145).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { components } from '@/generated/api';

type StandoffView = components['schemas']['StandoffView'];

const mutateAsync = vi.fn();
vi.mock('@/combat/queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/combat/queries')>();
  return { ...actual, useDispatchPlayerAction: () => ({ mutateAsync, isPending: false }) };
});

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

import { combatKeys } from '@/combat/queries';
import { StandoffCard } from '../StandoffCard';

const STANDOFF: StandoffView = {
  place: 'Test Place',
  groups: [
    {
      group_id: 11,
      name: 'Test Group',
      member_count: 4,
      state: 'open',
      terms_ease: 2,
      cause: 'Test cause',
      cause_gloss: 'Test gloss.',
      hidden_count: 3,
      drives: [{ label: 'Test drive', strength: 'minor' }],
      revealed_regard: [],
      read_check: 'Test read check',
      read_grade: 'moderate',
      read_grade_label: 'Moderate',
    },
  ],
  approaches: [
    {
      approach_id: 21,
      group_id: 11,
      name: 'Test approach',
      grade: 'easy',
      grade_label: 'Easy',
      check_caption: 'Test check + Test sway',
      levers: ['hits Test drive (Minor)', 'your spark: Test detail'],
      hits_revealed_drive: true,
    },
    {
      approach_id: 22,
      group_id: 11,
      name: 'Plain approach',
      grade: 'very_hard',
      grade_label: 'Very Hard',
      check_caption: 'Plain check',
      levers: [],
      hits_revealed_drive: false,
    },
  ],
  terms: [
    {
      terms_id: 31,
      name: 'Test terms',
      group_id: 11,
      description: 'Test terms outcome.',
      grade: 'hard',
      grade_label: 'Hard',
    },
  ],
  sparks: [{ group_id: 11, regard_rule_id: 41, text: 'Test spark', shared: false }],
  shared_sparks: [],
};

let client: QueryClient;
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderCard(standoff: StandoffView = STANDOFF) {
  return render(<StandoffCard standoff={standoff} encounterId={5} characterId={7} />, { wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mutateAsync.mockResolvedValue({
    backend: 'registry',
    deferred: false,
    message: 'Done.',
    success: true,
  });
});

describe('StandoffCard', () => {
  it('renders one face-down tile per hidden_count and the revealed cause and drive', () => {
    renderCard();
    expect(screen.getAllByTestId('standoff-facedown-tile')).toHaveLength(3);
    expect(screen.getByText('Test cause')).toBeInTheDocument();
    expect(screen.getByText('Test drive')).toBeInTheDocument();
    expect(screen.getByText(/Test Group/)).toBeInTheDocument();
    expect(screen.getByText(/4/)).toBeInTheDocument();
  });

  it('renders the own spark and shares it', async () => {
    const user = userEvent.setup();
    renderCard();
    expect(screen.getByText('Test spark')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Share with the party' }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_share_spark' },
      kwargs: { group_id: 11, regard_rule_id: 41 },
    });
  });

  it('presses an approach and invalidates the encounter', async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(client, 'invalidateQueries');
    renderCard();
    expect(screen.getByText('hits Test drive (Minor)')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Test approach/ }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_press' },
      kwargs: { group_id: 11, approach_id: 21 },
    });
    await waitFor(() => expect(spy).toHaveBeenCalledWith({ queryKey: combatKeys.encounter(5) }));
    expect(toastSuccess).toHaveBeenCalledWith('Done.', { className: 'whitespace-pre-line' });
  });

  it('opens a confirm step for terms and spins only on the spin button', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByRole('button', { name: /Test terms/ }));
    expect(mutateAsync).not.toHaveBeenCalled();
    const confirm = screen.getByTestId('standoff-terms-confirm');
    expect(within(confirm).getByText('Test terms outcome.')).toBeInTheDocument();
    await user.click(within(confirm).getByRole('button', { name: 'Spin for "Test terms"' }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_terms' },
      kwargs: { group_id: 11, terms_id: 31 },
    });
    expect(screen.queryByTestId('standoff-terms-confirm')).toBeNull();
  });

  it('keeps pressing without naming terms', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByRole('button', { name: /Test terms/ }));
    await user.click(screen.getByRole('button', { name: 'Keep pressing' }));
    expect(screen.queryByTestId('standoff-terms-confirm')).toBeNull();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('shows grade labels, never the raw enum value', () => {
    renderCard();
    const grades = screen.getAllByTestId('standoff-grade').map((g) => g.textContent);
    expect(grades).toEqual(['Moderate', 'Easy', 'Very Hard', 'Hard']);
    expect(document.body.textContent).not.toMatch(/very_hard/);
    const colours = screen.getAllByTestId('standoff-grade').map((g) => g.className);
    expect(colours[1]).toMatch(/emerald/);
    expect(colours[0]).toMatch(/amber/);
    expect(colours[2]).toMatch(/red/);
  });

  it('shows each approach check caption and the read check', () => {
    renderCard();
    expect(screen.getByText('Test check + Test sway')).toBeInTheDocument();
    expect(screen.getByText('Plain check')).toBeInTheDocument();
    expect(screen.getByText(/Test read check/)).toBeInTheDocument();
  });

  it('highlights an approach that hits a revealed drive and says no known lever otherwise', () => {
    renderCard();
    const hit = screen.getByTestId('standoff-approach-hit');
    expect(hit).toHaveTextContent('Test approach');
    expect(hit.className).toMatch(/border-accent/);
    expect(within(hit).getByText('your spark: Test detail')).toBeInTheDocument();
    const plain = screen.getByRole('button', { name: /Plain approach/ });
    expect(plain.className).not.toMatch(/border-accent/);
    expect(within(plain).getByText('no known lever')).toBeInTheDocument();
  });

  it('hints at the spark until a read reveals it', () => {
    const { unmount } = renderCard();
    expect(screen.getByText(/How, you don.t know yet/)).toBeInTheDocument();
    unmount();
    renderCard({
      ...STANDOFF,
      groups: [{ ...STANDOFF.groups[0], revealed_regard: ['Test detail.'] }],
    });
    expect(screen.queryByText(/How, you don.t know yet/)).toBeNull();
  });

  it('labels the read row "Read them again" only once something was read', () => {
    const { unmount } = renderCard();
    expect(screen.getByRole('button', { name: /^Read them again/ })).toBeInTheDocument();
    unmount();
    renderCard({
      ...STANDOFF,
      groups: [{ ...STANDOFF.groups[0], cause: null, drives: [], revealed_regard: [] }],
    });
    expect(screen.queryByRole('button', { name: /^Read them again/ })).toBeNull();
  });

  it('keeps option rows readable on hover (muted fill, text colours kept)', () => {
    renderCard();
    for (const name of [/Test approach/, /Test terms/, /^Read them/, /^Fight/]) {
      const cls = screen.getByRole('button', { name }).className;
      expect(cls).toMatch(/hover:bg-muted/);
      expect(cls).not.toMatch(/hover:bg-accent/);
    }
  });

  it('glosses the revealed cause and shows the place', () => {
    renderCard();
    expect(screen.getByText('Test gloss.')).toBeInTheDocument();
    expect(screen.getByText(/at Test Place/)).toBeInTheDocument();
  });

  it('draws the fight row as an outline with its caption and no morale', () => {
    renderCard();
    const fight = screen.getByTestId('standoff-fight');
    expect(fight).toHaveTextContent('starts round one');
    expect(fight.className).toMatch(/border-destructive/);
    expect(fight.className).not.toMatch(/bg-destructive/);
    expect(document.body.textContent).not.toMatch(/morale/i);
  });

  it('fights', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByRole('button', { name: /^Fight/ }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_fight' },
      kwargs: {},
    });
  });

  it('reads with no focus by default', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByRole('button', { name: /^Read them/ }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_read' },
      kwargs: { group_id: 11 },
    });
  });

  it('reads with a chosen focus', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByLabelText('Look for'));
    await user.click(screen.getByRole('option', { name: 'What moves them?' }));
    await user.click(screen.getByRole('button', { name: /^Read them/ }));
    expect(mutateAsync).toHaveBeenLastCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_read' },
      kwargs: { group_id: 11, focus_kind: 'drive' },
    });
  });

  it('offers an own spark as a read focus', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByLabelText('Look for'));
    await user.click(screen.getByRole('option', { name: 'Test spark' }));
    await user.click(screen.getByRole('button', { name: /^Read them/ }));
    expect(mutateAsync).toHaveBeenLastCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_read' },
      kwargs: { group_id: 11, focus_kind: 'regard', focus_regard_rule_id: 41 },
    });
  });

  it('toasts the message of a failed action', async () => {
    const user = userEvent.setup();
    mutateAsync.mockResolvedValue({
      backend: 'registry',
      deferred: false,
      message: 'Too late.',
      success: false,
    });
    renderCard();
    await user.click(screen.getByRole('button', { name: /^Fight/ }));
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('Too late.', {
        className: 'whitespace-pre-line',
      })
    );
    expect(within(document.body).queryByText('Done.')).toBeNull();
  });

  it('keeps each learned line of a multi-line result on its own line', async () => {
    const user = userEvent.setup();
    mutateAsync.mockResolvedValue({
      backend: 'registry',
      deferred: false,
      message: 'First line.\nSecond line.',
      success: true,
    });
    renderCard();
    await user.click(screen.getByRole('button', { name: /^Fight/ }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    const [message, options] = toastSuccess.mock.calls[0];
    expect(message).toContain('\n');
    expect(options).toEqual({ className: 'whitespace-pre-line' });
  });

  it('disables read, approaches and terms once the group is not open', () => {
    renderCard({ ...STANDOFF, groups: [{ ...STANDOFF.groups[0], state: 'settled' }] });
    expect(screen.getByRole('button', { name: /^Read them/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Test approach/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Test terms/ })).toBeDisabled();
  });

  it('disables read when nothing is left hidden', () => {
    renderCard({ ...STANDOFF, groups: [{ ...STANDOFF.groups[0], hidden_count: 0 }] });
    expect(screen.getByRole('button', { name: /^Read them/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Test approach/ })).toBeEnabled();
  });

  it('labels the tiles for assistive tech', () => {
    renderCard();
    expect(screen.getAllByRole('img', { name: /Hidden/ })).toHaveLength(3);
    expect(screen.getByRole('group', { name: 'What is known' })).toBeInTheDocument();
  });
});
