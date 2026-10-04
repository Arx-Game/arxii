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
  groups: [
    {
      group_id: 11,
      name: 'Test Group',
      member_count: 4,
      state: 'open',
      terms_ease: 2,
      cause: 'Test cause',
      hidden_count: 3,
      drives: [{ label: 'Test drive', strength: 'minor' }],
      revealed_regard: [],
    },
  ],
  approaches: [
    { approach_id: 21, group_id: 11, name: 'Test approach', grade: 'Easy', levers: ['lever one'] },
  ],
  terms: [{ terms_id: 31, name: 'Test terms', group_id: 11, grade: 'Hard' }],
  sparks: [{ group_id: 11, regard_rule_id: 41, text: 'Test spark', shared: false }],
  shared_sparks: [],
  owner_options: [],
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
    expect(screen.getByText('lever one')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Test approach/ }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_press' },
      kwargs: { group_id: 11, approach_id: 21 },
    });
    await waitFor(() => expect(spy).toHaveBeenCalledWith({ queryKey: combatKeys.encounter(5) }));
    expect(toastSuccess).toHaveBeenCalledWith('Done.', { className: 'whitespace-pre-line' });
  });

  it('names terms', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByRole('button', { name: /Test terms/ }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_terms' },
      kwargs: { group_id: 11, terms_id: 31 },
    });
  });

  it('fights', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByRole('button', { name: 'Fight' }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'standoff_fight' },
      kwargs: {},
    });
  });

  it('reads with no focus by default', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByRole('button', { name: 'Read them' }));
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
    await user.click(screen.getByRole('button', { name: 'Read them' }));
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
    await user.click(screen.getByRole('button', { name: 'Read them' }));
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
    await user.click(screen.getByRole('button', { name: 'Fight' }));
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
    await user.click(screen.getByRole('button', { name: 'Fight' }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    const [message, options] = toastSuccess.mock.calls[0];
    expect(message).toContain('\n');
    expect(options).toEqual({ className: 'whitespace-pre-line' });
  });

  it('disables read, approaches and terms once the group is not open', () => {
    renderCard({ ...STANDOFF, groups: [{ ...STANDOFF.groups[0], state: 'settled' }] });
    expect(screen.getByRole('button', { name: 'Read them' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Test approach/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Test terms/ })).toBeDisabled();
  });

  it('disables read when nothing is left hidden', () => {
    renderCard({ ...STANDOFF, groups: [{ ...STANDOFF.groups[0], hidden_count: 0 }] });
    expect(screen.getByRole('button', { name: 'Read them' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Test approach/ })).toBeEnabled();
  });

  it('labels the tiles for assistive tech', () => {
    renderCard();
    expect(screen.getAllByRole('img', { name: /Hidden/ })).toHaveLength(3);
    expect(screen.getByRole('group', { name: 'What is known' })).toBeInTheDocument();
  });
});
