/**
 * GlimpseSection Component Tests (#2427; folio-grammar fix round 1; one bonus
 * from each of four parts, three ways in and no CG points, #5292).
 *
 * Mirrors GiftSelector.test.tsx's mock/provider setup: the catalog and copy
 * queries are pre-seeded, and the API module is mocked so only updateDraft is
 * actually exercised.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import type { TagOffer } from '@/magic/components/glimpse/glimpseTypes';
import { unreachableClasses } from '../offers/classGuard';
import { GlimpseSection } from '../../../components/gift/GlimpseSection';
import { characterCreationKeys } from '../../../queries';
import type { CGExplanations, CharacterDraft, GlimpseTagOption } from '../../../types';
import { createMockDraft, mockBeginnings } from '../../fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from '../../testUtils';

const updateDraftMock = vi.fn();

// getGlimpseTags/getCGExplanations are never invoked because the query caches
// are pre-seeded below.
vi.mock('../../../api', () => ({
  getGlimpseTags: vi.fn(),
  getDraftOffers: vi.fn(),
  getCGExplanations: vi.fn(),
  updateDraft: (...args: unknown[]) => updateDraftMock(...args),
}));

function card(name: string, effectLine: string): TagOffer {
  return {
    offer_id: 900 + name.length,
    distinction_id: 900 + name.length,
    name,
    player_line: '',
    cost_per_rank: 20,
    max_rank: 1,
    effect_line: effectLine,
  };
}

function answer(
  id: number,
  axis: GlimpseTagOption['axis'],
  name: string,
  description: string,
  offers: TagOffer[] = []
): GlimpseTagOption {
  return {
    id,
    axis,
    name,
    slug: name.toLowerCase().replace(/\W+/g, '-'),
    description,
    example: '',
    sort_order: id,
    stands_alone: false,
    offers,
  };
}

const TRIGGER_CRISIS = answer(6, 'TRIGGER', 'Crisis', 'Magic woke when you needed more.', [
  card('Crisisborn', '+Resolve'),
]);
const REFLECTION_RADIANT = answer(8, 'REFLECTION', 'Radiant', 'You saw yourself shining.', [
  card('Glimmering', '+Presence'),
]);
const TONE_WONDER = answer(1, 'TONE', 'Wonder', 'Awe at the impossible.', [
  card('Wonderstruck', '+Anima'),
]);
// An answer with no card: it gives nothing, and nothing stands in for the card.
const TONE_GRIEF = answer(2, 'TONE', 'Grief', 'It came with a loss.');
const CONSEQUENCE_A = answer(3, 'CONSEQUENCE', 'A Debt Incurred', 'Something was owed after.', [
  card('Indebted', '-Composure'),
]);
const CONSEQUENCE_B = answer(4, 'CONSEQUENCE', 'A Door Opened', 'Something new became possible.');
const WITNESS_ALONE = answer(5, 'WITNESS', 'Alone', 'No one else saw.');

const CATALOG: GlimpseTagOption[] = [
  TRIGGER_CRISIS,
  REFLECTION_RADIANT,
  TONE_WONDER,
  TONE_GRIEF,
  CONSEQUENCE_A,
  CONSEQUENCE_B,
  WITNESS_ALONE,
];

function renderSection(draft: CharacterDraft, copy: CGExplanations = {}) {
  const queryClient = createTestQueryClient();
  seedQueryData(queryClient, characterCreationKeys.glimpseTags(), CATALOG);
  seedQueryData(queryClient, characterCreationKeys.explanations(), copy);
  const glimpseProseField = {
    name: 'glimpse_story' as const,
    onChange: vi.fn(),
    onBlur: vi.fn(),
    ref: vi.fn(),
  };
  const result = renderWithCharacterCreationProviders(
    <div className="interview">
      <GlimpseSection draft={draft} glimpseProseField={glimpseProseField} />
    </div>,
    { queryClient }
  );
  return { ...result, glimpseProseField };
}

function expectSaved(draftData: Record<string, unknown>) {
  return waitFor(() => {
    expect(updateDraftMock).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ draft_data: expect.objectContaining(draftData) })
    );
  });
}

describe('GlimpseSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateDraftMock.mockResolvedValue({});
  });

  describe('the parts', () => {
    it('draws every part at once, in the order they are asked, an answer button for each tag', () => {
      renderSection(createMockDraft({ id: 1, draft_data: {} }));

      const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
      expect(titles).toEqual([
        'Trigger',
        'The Reflection',
        'Tone',
        'Consequence',
        'Witness & Secrecy',
      ]);
      for (const tag of CATALOG) {
        expect(screen.getByRole('button', { name: new RegExp(tag.name) })).toBeInTheDocument();
      }
    });

    it('heads a part with a title in the larger style, the same for a part that gives no card', () => {
      renderSection(createMockDraft({ id: 1, draft_data: {} }));

      for (const title of ['Trigger', 'Witness & Secrecy']) {
        const group = screen.getByRole('group', { name: title });
        expect(group).toHaveClass('field', 'part');
      }
    });

    it('reads the lead-in under a title until the part has an explanation, which replaces it', () => {
      renderSection(createMockDraft({ id: 1, draft_data: {} }), {
        glimpse_axis_tone_explanation: 'What the moment felt like from inside.',
      });

      const tone = screen.getByRole('group', { name: 'Tone' });
      expect(within(tone).getByText('What the moment felt like from inside.')).toHaveClass(
        'explain'
      );
      expect(within(tone).queryByText('How It Felt:')).not.toBeInTheDocument();
      // A part with no explanation written yet keeps its lead-in, so it is never bare.
      const trigger = screen.getByRole('group', { name: 'Trigger' });
      expect(within(trigger).getByText('The Circumstances Around Your Glimpse:')).toHaveClass(
        'lead-in'
      );
    });

    it('every part takes one answer: round marks, and nothing says "choose any"', () => {
      const { container } = renderSection(createMockDraft({ id: 1, draft_data: {} }));

      expect(screen.queryByText('choose any')).not.toBeInTheDocument();
      expect(screen.queryByText('choose one')).not.toBeInTheDocument();
      expect(container.querySelectorAll('.part .dot.sq')).toHaveLength(0);
      expect(container.querySelectorAll('.part ul.stances.oneof')).toHaveLength(5);
    });

    it("lays a part's answers out as the life page's cards, one list item each (#5191)", () => {
      renderSection(createMockDraft({ id: 1, draft_data: {} }));

      const tone = screen.getByRole('group', { name: 'Tone' });
      const list = within(tone).getByRole('list');
      expect(list).toHaveClass('stances', 'grid', 'pair');
      expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    });

    it('picking an answer PATCHes draft_data.glimpse_tag_ids', async () => {
      const user = userEvent.setup();
      renderSection(createMockDraft({ id: 1, draft_data: {} }));

      await user.click(screen.getByRole('button', { name: /Wonder/ }));

      await expectSaved({ glimpse_tag_ids: [1] });
    });

    it('a second answer in a part replaces the first, in a part that used to take several', async () => {
      const user = userEvent.setup();
      renderSection(createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [1, 3] } }));

      await user.click(screen.getByRole('button', { name: /A Door Opened/ }));

      // Consequence swaps 3 for 4; Tone's answer is untouched.
      await expectSaved({ glimpse_tag_ids: [1, 4] });
    });

    it('picking the chosen answer again lets it go', async () => {
      const user = userEvent.setup();
      renderSection(createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [1, 3] } }));

      await user.click(screen.getByRole('button', { name: /Wonder/ }));

      await expectSaved({ glimpse_tag_ids: [3] });
    });

    it('selects an answer via the keyboard (Enter, native button semantics)', async () => {
      const user = userEvent.setup();
      renderSection(createMockDraft({ id: 1, draft_data: {} }));

      screen.getByRole('button', { name: /Wonder/ }).focus();
      await user.keyboard('{Enter}');

      await expectSaved({ glimpse_tag_ids: [1] });
    });
  });

  describe('the card an answer gives', () => {
    it('shows the card on the answer before it is picked: its name and its mechanics line', () => {
      renderSection(createMockDraft({ id: 1, draft_data: {} }));

      const wonder = screen.getByRole('button', { name: /Wonder/ });
      expect(wonder).toHaveAttribute('aria-pressed', 'false');
      const bonus = wonder.querySelector('.bonus');
      expect(bonus).toHaveTextContent('Wonderstruck');
      expect(bonus).toHaveTextContent('+Anima');
    });

    it('an answer with no card shows only its own words', () => {
      renderSection(createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [2] } }));

      const grief = screen.getByRole('button', { name: /Grief/ });
      expect(grief).toHaveAttribute('aria-pressed', 'true');
      expect(grief.querySelector('.bonus')).toBeNull();
      expect(grief).toHaveTextContent('GriefIt came with a loss.');
    });

    it('a picked answer opens no second list, no price and nothing else to pick', () => {
      const { container } = renderSection(
        createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [1, 3] } })
      );

      expect(container.querySelector('.conditional')).toBeNull();
      expect(container.querySelector('.price')).toBeNull();
      expect(screen.queryByText('optional')).not.toBeInTheDocument();
      expect(screen.queryByText('What it left in you')).not.toBeInTheDocument();
    });
  });

  describe('the three ways into the Glimpse', () => {
    it('offers the three ways under the owner’s labels, the first chosen on a new draft', () => {
      renderSection(createMockDraft({ id: 1, draft_data: {} }));

      const pressed = (name: string) =>
        screen.getByRole('button', { name }).getAttribute('aria-pressed');
      expect(pressed('Create Glimpse in CG')).toBe('true');
      expect(pressed('Amnesiac, No Memory of Glimpse')).toBe('false');
      expect(pressed('Create Glimpse Post-CG')).toBe('false');
    });

    it('opens on the owner’s paragraph, without the sentence that promised CG points', () => {
      renderSection(createMockDraft({ id: 1, draft_data: {} }));

      const intro = screen.getByText(/The Glimpse is the often traumatic event/);
      expect(intro).toHaveClass('explain');
      expect(intro).toHaveTextContent(/may have no memory of this\.$/);
      expect(screen.queryByText(/CG points/)).not.toBeInTheDocument();
    });

    it('a copy row replaces the paragraph', () => {
      renderSection(createMockDraft({ id: 1, draft_data: {} }), {
        glimpse_intro: 'The owner rewrote this.',
      });

      expect(screen.getByText('The owner rewrote this.')).toBeInTheDocument();
      expect(screen.queryByText(/often traumatic event/)).not.toBeInTheDocument();
    });

    it('choosing the amnesiac way saves no memory', async () => {
      const user = userEvent.setup();
      renderSection(createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [1] } }));

      await user.click(screen.getByRole('button', { name: 'Amnesiac, No Memory of Glimpse' }));

      await expectSaved({ glimpse_memory: 'no_memory' });
      // The answers are not cleared: they stay in the draft for a change of mind.
      expect(updateDraftMock).toHaveBeenCalledTimes(1);
      expect(updateDraftMock.mock.calls[0][1].draft_data).not.toHaveProperty('glimpse_tag_ids');
    });

    it('with no memory no part is asked, and one line says what the choice means', () => {
      renderSection(
        createMockDraft({
          id: 1,
          draft_data: { glimpse_memory: 'no_memory', glimpse_tag_ids: [1] },
        })
      );

      expect(screen.queryAllByRole('heading', { level: 3 })).toHaveLength(0);
      expect(screen.queryByLabelText('Your story')).not.toBeInTheDocument();
      expect(screen.getByText(/Nothing of the Glimpse is asked/)).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Amnesiac, No Memory of Glimpse' })
      ).toHaveAttribute('aria-pressed', 'true');
    });

    it('with the Glimpse left for after creation no part is asked either', async () => {
      const user = userEvent.setup();
      const { unmount } = renderSection(createMockDraft({ id: 1, draft_data: {} }));
      await user.click(screen.getByRole('button', { name: 'Create Glimpse Post-CG' }));
      await expectSaved({ glimpse_memory: 'later' });
      unmount();

      renderSection(createMockDraft({ id: 1, draft_data: { glimpse_memory: 'later' } }));
      expect(screen.queryAllByRole('heading', { level: 3 })).toHaveLength(0);
      expect(screen.getByText(/written from the character sheet after/)).toBeInTheDocument();
    });

    it('going back to the first way saves remembered', async () => {
      const user = userEvent.setup();
      renderSection(createMockDraft({ id: 1, draft_data: { glimpse_memory: 'later' } }));

      await user.click(screen.getByRole('button', { name: 'Create Glimpse in CG' }));

      await expectSaved({ glimpse_memory: 'remembered' });
    });

    it('"Skip for now" is gone: the third way is that choice', () => {
      renderSection(createMockDraft({ id: 1, draft_data: {} }));

      expect(screen.queryByText(/Skip for now/)).not.toBeInTheDocument();
      expect(screen.queryByText(/set aside for now/)).not.toBeInTheDocument();
    });

    it('a beginning with no memory of the Glimpse shows no ways and no parts', () => {
      renderSection(
        createMockDraft({
          id: 1,
          selected_beginnings: { ...mockBeginnings, no_glimpse_memory: true },
          // Whatever the draft holds, such a beginning has no memory.
          draft_data: { glimpse_memory: 'remembered', glimpse_tag_ids: [1] },
        })
      );

      expect(
        screen.queryByRole('button', { name: 'Create Glimpse in CG' })
      ).not.toBeInTheDocument();
      expect(screen.queryAllByRole('heading', { level: 3 })).toHaveLength(0);
      expect(screen.getByText(/Nothing of the Glimpse is asked/)).toBeInTheDocument();
    });
  });

  describe('the blackout', () => {
    it('sits between Trigger and The Reflection with the owner’s words, as a tick', () => {
      const { container } = renderSection(createMockDraft({ id: 1, draft_data: {} }));

      const tick = screen.getByRole('button', { name: /Blacked out/ });
      expect(tick).toHaveAttribute('aria-pressed', 'false');
      expect(tick).toHaveTextContent('You gain the Glimpse Mystery distinction.');
      expect(tick.querySelector('.dot.sq')).not.toBeNull();
      const order = [...container.querySelectorAll('h3, ul.blackout')].map((node) =>
        node.tagName === 'UL' ? 'blackout' : node.textContent
      );
      expect(order.slice(0, 3)).toEqual(['Trigger', 'blackout', 'The Reflection']);
    });

    it('ticking it saves blacked out, and unticking saves remembered', async () => {
      const user = userEvent.setup();
      const { unmount } = renderSection(createMockDraft({ id: 1, draft_data: {} }));
      await user.click(screen.getByRole('button', { name: /Blacked out/ }));
      await expectSaved({ glimpse_memory: 'blacked_out' });
      unmount();
      updateDraftMock.mockClear();

      renderSection(createMockDraft({ id: 1, draft_data: { glimpse_memory: 'blacked_out' } }));
      await user.click(screen.getByRole('button', { name: /Blacked out/ }));
      await expectSaved({ glimpse_memory: 'remembered' });
    });

    it('ticked, The Reflection and Tone are not shown and the other parts still are', () => {
      renderSection(
        createMockDraft({
          id: 1,
          draft_data: { glimpse_memory: 'blacked_out', glimpse_tag_ids: [1, 8] },
        })
      );

      const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
      expect(titles).toEqual(['Trigger', 'Consequence', 'Witness & Secrecy']);
      expect(screen.getByRole('button', { name: /Blacked out/ })).toHaveAttribute(
        'aria-pressed',
        'true'
      );
      // Still the first way: a blackout is not amnesia.
      expect(screen.getByRole('button', { name: 'Create Glimpse in CG' })).toHaveAttribute(
        'aria-pressed',
        'true'
      );
      expect(screen.getByLabelText('Your story')).toBeInTheDocument();
    });
  });

  it('registers the prose textarea under glimpse_story via the passed-down field', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      id: 1,
      draft_data: { glimpse_story: 'Once, in the dark' },
    });
    const { glimpseProseField } = renderSection(draft);

    const textarea = screen.getByLabelText('Your story') as HTMLTextAreaElement;
    expect(textarea.value).toBe('Once, in the dark');

    await user.type(textarea, '!');

    expect(glimpseProseField.onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        target: expect.objectContaining({ name: 'glimpse_story' }),
      })
    );
  });

  it('renders the default story hint under the story textarea', () => {
    renderSection(createMockDraft({ id: 1, draft_data: {} }));

    expect(
      screen.getByText('The detail behind any of the picks above goes here; the picks stay short.')
    ).toBeInTheDocument();
  });

  it('renders no heading of its own: the h2 above this mount is GiftStage’s job', () => {
    renderSection(createMockDraft({ id: 1, draft_data: {} }));

    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument();
    expect(screen.queryByText('The Glimpse')).not.toBeInTheDocument();
  });

  it('emits no class hook that cg.css has no rule reaching it (#3667 shape)', () => {
    for (const draftData of [
      { glimpse_tag_ids: [1, 3] },
      { glimpse_memory: 'blacked_out' as const },
      { glimpse_memory: 'no_memory' as const },
    ]) {
      const { container, unmount } = renderSection(
        createMockDraft({ id: 1, draft_data: draftData }),
        { glimpse_axis_tone_explanation: 'An explanation.' }
      );
      expect(unreachableClasses(container)).toEqual([]);
      unmount();
    }
  });
});
