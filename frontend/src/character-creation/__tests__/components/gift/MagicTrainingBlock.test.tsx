/**
 * MagicTrainingBlock Component Tests (#4659)
 *
 * The Gift stage's "What <Tradition> taught you" block: the training breakdown,
 * the spend ledger, and one Magic skill row per skill whose steppers PATCH the
 * whole `draft_data.magic_skills` map.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { MagicTrainingBlock } from '../../../components/gift/MagicTrainingBlock';
import { characterCreationKeys } from '../../../queries';
import type { CharacterDraft, MagicTraining } from '../../../types';
import { createMockDraft, mockTradition } from '../../fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from '../../testUtils';

const updateDraftMock = vi.fn();

vi.mock('../../../api', () => ({
  getCGExplanations: vi.fn(),
  updateDraft: (...args: unknown[]) => updateDraftMock(...args),
}));

const training: MagicTraining = {
  base_sources: [
    { name: 'Tradition Training', rank: 1, points: 20, show_rank: true },
    { name: 'Studious', rank: 1, points: 10, show_rank: false },
  ],
  gift_bonus: 10,
  affinity_bonus: 10,
  favored_gift_name: 'Shadowcraft',
  favored_affinity_name: 'Abyssal',
  total: 50,
  required_spend: 50,
  step: 10,
  allocated: 50,
  skills: [
    { id: 3, name: 'Occult', value: 30, max: 30 },
    { id: 4, name: 'Ritualism', value: 20, max: 30 },
    { id: 5, name: 'Theology', value: 0, max: 30 },
  ],
};

function draftWith(magic: MagicTraining): CharacterDraft {
  return createMockDraft({
    id: 1,
    selected_tradition: mockTradition,
    magic_training: magic,
    draft_data: { magic_skills: { '3': 30, '4': 20 } },
  });
}

function renderBlock(draft: CharacterDraft, copy: Record<string, string> = {}) {
  const queryClient = createTestQueryClient();
  seedQueryData(queryClient, characterCreationKeys.explanations(), copy);
  return renderWithCharacterCreationProviders(<MagicTrainingBlock draft={draft} />, {
    queryClient,
  });
}

describe('MagicTrainingBlock', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateDraftMock.mockResolvedValue({});
  });

  it('lists each source, each fit and the total, and reads Remaining 0 when spent exactly', () => {
    renderBlock(draftWith(training));

    expect(screen.getByText('Tradition Training, rank 1')).toBeInTheDocument();
    // A one-rank distinction is named without its rank, per the server's show_rank.
    expect(screen.getByText('Studious')).toBeInTheDocument();
    expect(screen.queryByText('Studious, rank 1')).not.toBeInTheDocument();
    expect(screen.getByText('Fits: Shadowcraft')).toBeInTheDocument();
    expect(screen.getByText('Fits: Abyssal')).toBeInTheDocument();
    expect(screen.getByText('Magical training')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('Spend all of it')).toBeInTheDocument();
    expect(screen.getByText(/Remaining/)).toHaveTextContent('Remaining 0');
    expect(screen.getByText(/Remaining/)).not.toHaveClass('over');
    expect(screen.getByLabelText('Occult')).toHaveTextContent('30');
  });

  it('flags an underspent pool the same way as an overspent one', () => {
    renderBlock(draftWith({ ...training, allocated: 30, skills: training.skills.slice(0, 2) }));

    const ledger = screen.getByText(/Remaining/);
    expect(ledger).toHaveTextContent('Remaining 20');
    expect(ledger).toHaveClass('over');
  });

  it('reads Over by 10 when the allocation is over the total', () => {
    renderBlock(
      draftWith({
        ...training,
        gift_bonus: 0,
        favored_gift_name: null,
        total: 40,
        required_spend: 40,
      })
    );

    expect(screen.queryByText('Fits: Shadowcraft')).not.toBeInTheDocument();
    expect(screen.getByText(/Over by/)).toHaveTextContent('Over by 10');
    expect(screen.getByText(/Over by/)).toHaveClass('over');
  });

  it('disables + on a skill at its cap, with the cap tooltip, while another can still rise', () => {
    renderBlock(draftWith({ ...training, allocated: 40, skills: training.skills.slice(0, 2) }));

    // Occult sits at its max of 30; Ritualism has room and 10 is left.
    const occult = screen.getByRole('button', { name: 'Raise Occult' });
    expect(occult).toBeDisabled();
    expect(occult).toHaveAttribute('title', 'At 30, the most it can be');
    expect(screen.getByRole('button', { name: 'Raise Ritualism' })).toBeEnabled();
  });

  it('disables + on every skill once the pool is spent', () => {
    renderBlock(draftWith(training));

    expect(screen.getByRole('button', { name: 'Raise Theology' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Lower Ritualism' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Lower Theology' })).toBeDisabled();
  });

  it('clicking + PATCHes the whole magic_skills map with the next value', async () => {
    const user = userEvent.setup();
    renderBlock(draftWith({ ...training, allocated: 40, skills: training.skills.slice(0, 2) }));

    await user.click(screen.getByRole('button', { name: 'Raise Ritualism' }));

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(1, {
        draft_data: { magic_skills: { '3': 30, '4': 30 } },
      });
    });
  });

  it("steps by the payload's step, not a fixed ten", async () => {
    const user = userEvent.setup();
    renderBlock(
      draftWith({
        ...training,
        step: 5,
        allocated: 45,
        skills: [
          { id: 3, name: 'Occult', value: 30, max: 30 },
          { id: 4, name: 'Ritualism', value: 15, max: 30 },
        ],
      })
    );

    // 5 left: a step of 10 would disable +, a step of 5 allows it.
    const raise = screen.getByRole('button', { name: 'Raise Ritualism' });
    expect(raise).toBeEnabled();
    await user.click(raise);

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(1, {
        draft_data: { magic_skills: { '3': 30, '4': 20 } },
      });
    });
  });

  it('renders nothing when there is no training and nothing allocated', () => {
    const { container } = renderBlock(
      createMockDraft({ id: 1, selected_tradition: mockTradition })
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('reads its labels from the explanation copy when staff wrote them', () => {
    renderBlock(draftWith({ ...training, allocated: 40, skills: training.skills.slice(0, 2) }), {
      gift_training_source: '{name} (rank {rank})',
      gift_training_total: 'Training',
      gift_training_spend: 'Use it all',
      gift_training_fits: 'Suits: {name}',
      gift_training_at_cap: 'Full at {max}',
    });

    expect(screen.getByText('Tradition Training (rank 1)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Raise Occult' })).toHaveAttribute(
      'title',
      'Full at 30'
    );
    expect(screen.getByText('Training')).toBeInTheDocument();
    expect(screen.getByText('Use it all')).toBeInTheDocument();
    expect(screen.getByText('Suits: Shadowcraft')).toBeInTheDocument();
  });
});
