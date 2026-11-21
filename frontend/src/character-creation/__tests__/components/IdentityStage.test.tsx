/**
 * IdentityStage Component Tests
 *
 * Tests for the name line and the concept and quote fields. The Background is Final
 * Touches' (#5178): this stage neither shows nor saves it. The Personality block
 * (#5255) is this stage's own offered cards.
 */

import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { getDraftOffers, updateDraft } from '../../api';
import { IdentityStage } from '../../components/IdentityStage';
import {
  mockCGExplanations,
  mockDraftWithFamily,
  mockCompleteDraft,
  createMockDraft,
} from '../fixtures';
import {
  renderWithCharacterCreationProviders,
  createTestQueryClient,
  seedQueryData,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';
import type { VisibleOffer } from '../../types';
import { unreachableClasses } from './offers/classGuard';

// Mock the API module
vi.mock('../../api', () => ({
  updateDraft: vi.fn(),
  getCGExplanations: vi.fn(),
  getWorshippedBeings: vi.fn().mockResolvedValue([]),
  getDraftOffers: vi.fn().mockResolvedValue({ offers: [], terms: [] }),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: [] }),
  useSyncDistinctions: () => ({ mutate: syncMutate, pendingEntries: null }),
  usePendingSync: () => null,
}));

const syncMutate = vi.fn();

/** A card placed on the Identity stage (#5255). */
function identityCard(id: number, name: string, extra: Partial<VisibleOffer> = {}): VisibleOffer {
  return {
    offer_id: id,
    distinction_id: id,
    name,
    distinction_name: name,
    distinction_description: `${name} in a sentence.`,
    player_line: '',
    chapter: 'identity',
    arrives_as: 'choice',
    opener_label: 'Identity',
    cost_per_rank: 5,
    max_rank: 1,
    is_locked: false,
    lock_reason: '',
    opener_key: '',
    first_look: false,
    held: false,
    effect_line: '',
    taken_per_feature: false,
    cg_max_rank: 0,
    group: '',
    asks_figure_name: false,
    effects: [],
    ...extra,
  };
}

describe('IdentityStage', () => {
  describe('Character Name Section', () => {
    // The first name is asked on the Origin leaf (#4874, ruled 2026-10-19); this stage
    // shows how the name renders and asks for nothing.
    it('shows the name as a line, never as a field', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      expect(screen.queryByLabelText(/first name/i)).toBeNull();
      expect(screen.getByTestId('identity-name')).toHaveTextContent('Testchar Valardin');
    });

    it('displays full name preview with family name', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      // The preview moved from an inline "Full name:" paragraph to the record
      // rail's "Name" row (#3630); the rail lists chosen values only.
      expect(screen.getByText('Name', { selector: 'dt' })).toBeInTheDocument();
      expect(screen.getAllByText('Testchar Valardin').length).toBeGreaterThan(0);
    });

    it('shows only first name when no family', () => {
      const queryClient = createTestQueryClient();
      const orphanDraft = createMockDraft({
        ...mockCompleteDraft,
        family: null,
      });

      renderWithCharacterCreationProviders(<IdentityStage draft={orphanDraft} />, { queryClient });

      expect(screen.getByTestId('identity-name')).toHaveTextContent('Testchar');
    });

    it('says where the name is asked when there is none yet', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByTestId('identity-name')).toHaveTextContent(
        'No first name yet; it is asked on the first page.'
      );
      expect(screen.queryByText('Name', { selector: 'dt' })).toBeNull();
    });
  });

  it("has no personality field: the Actor's Sheet asks its questions instead (#3621)", () => {
    const queryClient = createTestQueryClient();

    renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
      queryClient,
    });

    expect(screen.queryByLabelText(/personality/i)).toBeNull();
  });

  it('saves the concept and the quote and never a background, so it cannot overwrite the one written on Final Touches (#5178)', async () => {
    const user = userEvent.setup();
    vi.mocked(updateDraft).mockResolvedValue(mockCompleteDraft);
    let leave: (() => Promise<boolean>) | null = null;
    const draft = createMockDraft({
      draft_data: { concept: 'A pilot', quote: '', background: 'Written on Final Touches.' },
    });
    renderWithCharacterCreationProviders(
      <IdentityStage
        draft={draft}
        onRegisterBeforeLeave={(check) => {
          leave = check;
        }}
      />,
      { queryClient: createTestQueryClient() }
    );
    expect(screen.queryByLabelText(/background/i)).toBeNull();
    await user.type(screen.getByLabelText(/character concept/i), ' of the lower river');
    await act(async () => {
      await leave!();
    });
    expect(updateDraft).toHaveBeenCalledTimes(1);
    const sent = vi.mocked(updateDraft).mock.calls[0][1].draft_data ?? {};
    expect(sent).toEqual({ concept: 'A pilot of the lower river', quote: '' });
    expect(sent).not.toHaveProperty('background');
  });

  describe('Concept Section', () => {
    it('displays concept input field', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByLabelText(/character concept/i)).toBeInTheDocument();
    });

    it('shows current concept value', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      const input = screen.getByLabelText(/character concept/i) as HTMLInputElement;
      expect(input.value).toBe('A warrior seeking redemption.');
    });
  });

  describe('Quote Section', () => {
    it('displays quote input field', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByLabelText(/character quote/i)).toBeInTheDocument();
    });

    it('shows current quote value', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      const input = screen.getByLabelText(/character quote/i) as HTMLInputElement;
      expect(input.value).toBe('The dawn comes for all.');
    });
  });

  describe('Page Header', () => {
    it('displays stage title and description', () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.explanations(), mockCGExplanations);

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByText('Identity')).toBeInTheDocument();
      expect(screen.getByText(/define your character.*s name and story/i)).toBeInTheDocument();
    });
  });

  describe('Personality cards (#5255)', () => {
    beforeEach(() => {
      syncMutate.mockClear();
      vi.mocked(getDraftOffers).mockResolvedValue({ offers: [], terms: [] });
    });

    it('shows no Personality section when no card is placed on Identity', async () => {
      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient: createTestQueryClient(),
      });
      await waitFor(() =>
        expect(getDraftOffers).toHaveBeenCalledWith(mockCompleteDraft.id, 'identity')
      );
      expect(screen.queryByRole('heading', { name: 'Personality' })).toBeNull();
    });

    it('lists the cards between the quote and worship and takes one on a click', async () => {
      const user = userEvent.setup();
      vi.mocked(getDraftOffers).mockResolvedValue({
        offers: [identityCard(1, 'Indolent'), identityCard(2, 'Tireless', { cost_per_rank: -5 })],
        terms: [],
      });
      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient: createTestQueryClient(),
      });

      const heading = await screen.findByRole('heading', { name: 'Personality' });
      const quote = screen.getByRole('heading', { name: 'Quote' });
      const worship = screen.getByRole('heading', { name: 'Worship' });
      expect(
        quote.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy();
      expect(
        heading.compareDocumentPosition(worship) & Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy();

      // The life page's cards: the name, the description under it, the price signed.
      const indolent = screen.getByRole('button', { name: /Indolent/ });
      expect(indolent).toHaveTextContent('Indolent in a sentence.');
      expect(indolent).toHaveTextContent('\u22125');
      expect(screen.getByRole('button', { name: /Tireless/ })).toHaveTextContent('+5');
      // Two across in the reading column, like the Glimpse's cards.
      expect(indolent.closest('ul')).toHaveClass('stances', 'grid', 'pair');

      await user.click(indolent);
      expect(syncMutate).toHaveBeenCalledTimes(1);
      expect(syncMutate.mock.calls[0][0]).toEqual([
        expect.objectContaining({ id: 1, offer_id: 1, rank: 1 }),
      ]);
    });

    it('shows four cards at rest and the rest, still as cards, under See more', async () => {
      const names = ['Daring', 'Efficient', 'Hedonistic', 'Indolent', 'Proud', 'Tireless'];
      vi.mocked(getDraftOffers).mockResolvedValue({
        offers: names.map((name, index) => identityCard(index + 1, name)),
        terms: [],
      });
      const { container } = renderWithCharacterCreationProviders(
        <div className="interview">
          <IdentityStage draft={mockCompleteDraft} />
        </div>,
        { queryClient: createTestQueryClient() }
      );

      await screen.findByRole('heading', { name: 'Personality' });
      const fold = screen.getByText('See 2 more').closest('details');
      expect(fold).not.toBeNull();
      const folded = fold!.querySelector('ul');
      expect(folded).toHaveClass('stances', 'grid', 'pair');
      expect(folded!.querySelectorAll('li')).toHaveLength(2);
      // Two full rows at rest: four cards, not the three a one-column block shows.
      expect(container.querySelectorAll('.offer-group ul.stances > li')).toHaveLength(4);
      // Every class the block emits has a rule in cg.css that reaches it (#3667 shape).
      const styledElsewhere = new Set(['leaf-body', 'note-group']);
      expect(unreachableClasses(container, styledElsewhere)).toEqual([]);
    });

    it('shows every card under its heading when staff grouped the lines', async () => {
      vi.mocked(getDraftOffers).mockResolvedValue({
        offers: [
          ...['Daring', 'Proud', 'Indolent'].map((name, index) =>
            identityCard(index + 1, name, { group: 'Temperament' })
          ),
          ...['Tireless', 'Efficient', 'Hedonistic'].map((name, index) =>
            identityCard(index + 10, name, { group: 'Habits' })
          ),
        ],
        terms: [],
      });
      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient: createTestQueryClient(),
      });

      await screen.findByRole('heading', { name: 'Personality' });
      expect(screen.getByText('Temperament (3)')).toBeInTheDocument();
      expect(screen.getByText('Habits (3)')).toBeInTheDocument();
      expect(screen.queryByText(/See \d+ more/)).toBeNull();
    });
  });

  describe('Folio markup', () => {
    it('renders the writing fields on the field idiom and the name as a line and in the rail', () => {
      const queryClient = createTestQueryClient();
      const draft = createMockDraft({ draft_data: { first_name: 'Sharlotte' } });

      renderWithCharacterCreationProviders(<IdentityStage draft={draft} />, { queryClient });

      // Sentence case (#3630): interface chrome is plain, and only the first
      // word is capitalised. The other blocks in this file query the same
      // labels case-insensitively, so they are unaffected.
      for (const label of ['Character concept', 'Character quote']) {
        expect(screen.getByLabelText(label).closest('.field')).not.toBeNull();
      }
      // The first name is asked on the Origin leaf (#4874); here it is a line, not a field.
      expect(screen.queryByLabelText('First name')).toBeNull();
      expect(screen.getByTestId('identity-name')).toHaveTextContent('Sharlotte');
      expect(screen.getByRole('heading', { name: 'CG selections' })).toBeInTheDocument();
      expect(screen.getAllByText('Sharlotte').length).toBeGreaterThan(0);
    });
  });
});
