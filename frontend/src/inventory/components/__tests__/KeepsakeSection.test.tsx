/**
 * The item panel's keepsake row and form (#4530): the trophy chip, what the item already stands
 * for, and the form that keeps it. The player's words are theirs; the form never scores them.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { KeepsakeState } from '../../api';
import type { ItemInstance } from '../../types';

const declareMutate = vi.fn();
const releaseMutate = vi.fn();
let stateData: KeepsakeState | undefined;

vi.mock('../../hooks/useKeepsake', () => ({
  useKeepsakeState: () => ({ data: stateData }),
  useDeclareKeepsake: () => ({ mutate: declareMutate, isPending: false }),
  useReleaseKeepsake: () => ({ mutate: releaseMutate, isPending: false }),
}));
vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: () => ({ results: [{ id: 9, name: 'Tamar' }], isFetching: false }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { KeepsakeSection } from '../KeepsakeSection';

const ITEM = { id: 7, display_name: 'frayed climbing rope' } as ItemInstance;

function baseState(overrides: Partial<KeepsakeState> = {}): KeepsakeState {
  return {
    keepsake: null,
    counts_now: false,
    status: { used: 2, limit: 5, wait_days: 14 },
    subjects: {
      tie: [{ id: 1, label: 'Tamar' }],
      deed: [{ id: 3, label: 'Cliff rescue' }],
      being: [{ id: 4, label: 'Highwind' }],
      organization: [],
    },
    trophy_of: [],
    carried_days: 70,
    ...overrides,
  };
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <KeepsakeSection item={ITEM} characterId={3} />
    </QueryClientProvider>
  );
}

describe('KeepsakeSection', () => {
  beforeEach(() => {
    declareMutate.mockReset();
    releaseMutate.mockReset();
    stateData = baseState();
  });

  it('shows the trophy chip and the slots in use', () => {
    stateData = baseState({ trophy_of: ['Cliff rescue'] });
    mount();

    expect(screen.getByTestId('trophy-chips')).toHaveTextContent('Trophy of Cliff rescue');
    expect(screen.getByTestId('keepsake-section')).toHaveTextContent('Keepsakes: 2 of 5 used.');
  });

  it('keeps an item for one of her deeds, in her own words', async () => {
    mount();
    await userEvent.click(screen.getByTestId('keepsake-open'));

    const form = screen.getByTestId('keepsake-form');
    expect(within(form).getByText('It stands for')).toBeInTheDocument();
    expect(within(form).getByTestId('keepsake-chips')).toHaveTextContent('carried 2 months');
    expect(form).toHaveTextContent(
      'Keepsakes: 2 of 5 used. A keepsake counts 14 days after you declare it. Its points come from the subject you choose. Nobody scores the words.'
    );
    const save = within(form).getByRole('button', { name: 'Save keepsake' });
    expect(save).toBeDisabled();

    await userEvent.selectOptions(within(form).getByLabelText('Which deed'), '3');
    await userEvent.type(within(form).getByLabelText(/In your words/), 'Her own words.');
    await userEvent.click(within(form).getByLabelText('Show on examine'));
    expect(save).toBeEnabled();
    await userEvent.click(save);

    await waitFor(() => expect(declareMutate).toHaveBeenCalled());
    expect(declareMutate.mock.calls[0][0]).toEqual({
      itemId: 7,
      subjectKind: 'deed',
      subjectId: 3,
      subjectLabel: undefined,
      text: 'Her own words.',
      shownOnExamine: true,
      treasured: false,
    });
  });

  it('names a place in free text and a person by search', async () => {
    mount();
    await userEvent.click(screen.getByTestId('keepsake-open'));
    const form = screen.getByTestId('keepsake-form');

    await userEvent.click(within(form).getByLabelText('a place'));
    await userEvent.type(within(form).getByLabelText('The place'), 'the harbor');
    await userEvent.type(within(form).getByLabelText(/In your words/), 'Her own words.');
    await userEvent.click(within(form).getByRole('button', { name: 'Save keepsake' }));
    expect(declareMutate.mock.calls[0][0]).toMatchObject({
      subjectKind: 'place',
      subjectLabel: 'the harbor',
      subjectId: undefined,
    });

    declareMutate.mockReset();
    await userEvent.click(within(form).getByLabelText('a person'));
    await userEvent.type(within(form).getByLabelText('Which person'), 'Ta');
    await userEvent.click(within(form).getByRole('button', { name: 'Tamar' }));
    await userEvent.click(within(form).getByRole('button', { name: 'Save keepsake' }));
    expect(declareMutate.mock.calls[0][0]).toMatchObject({ subjectKind: 'person', subjectId: 9 });
  });

  it('says when there is nothing of a kind to choose from', async () => {
    mount();
    await userEvent.click(screen.getByTestId('keepsake-open'));
    await userEvent.click(screen.getByLabelText('an organization'));

    expect(screen.getByTestId('keepsake-no-subjects')).toHaveTextContent(
      'You have none of these to choose from.'
    );
  });

  it('offers nothing to keep once every slot is used', () => {
    stateData = baseState({ status: { used: 5, limit: 5, wait_days: 14 } });
    mount();

    expect(screen.getByTestId('keepsake-open')).toBeDisabled();
  });

  it('shows what a kept item stands for and lets her release it', async () => {
    stateData = baseState({
      keepsake: {
        id: 1,
        subject_kind: 'deed',
        subject_name: 'the deed Cliff rescue',
        text: 'Her own words.',
        shown_on_examine: false,
        created_at: new Date().toISOString(),
      },
    });
    mount();

    const current = screen.getByTestId('keepsake-current');
    expect(current).toHaveTextContent('Kept as a keepsake of the deed Cliff rescue.');
    expect(current).toHaveTextContent('Her own words.');
    expect(current).toHaveTextContent('Your words are private');
    await userEvent.click(screen.getByTestId('keepsake-release'));
    expect(releaseMutate).toHaveBeenCalledWith(7, expect.anything());
  });
});
