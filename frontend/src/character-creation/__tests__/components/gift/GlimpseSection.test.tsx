/**
 * GlimpseSection Component Tests (#2427)
 *
 * Mirrors GiftSelector.test.tsx's mock/provider setup: the catalog and draft
 * distinctions queries are pre-seeded, and the API module is mocked so only
 * updateDraft is actually exercised.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { distinctionKeys } from '@/hooks/useDistinctions';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import { GlimpseSection } from '../../../components/gift/GlimpseSection';
import { characterCreationKeys } from '../../../queries';
import type { CharacterDraft, GlimpseTagOption } from '../../../types';
import { createMockDraft } from '../../fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from '../../testUtils';

const updateDraftMock = vi.fn();

// getGlimpseTags is never invoked because the query cache is pre-seeded below.
vi.mock('../../../api', () => ({
  getGlimpseTags: vi.fn(),
  updateDraft: (...args: unknown[]) => updateDraftMock(...args),
}));

const TONE_WONDER: GlimpseTagOption = {
  id: 1,
  axis: 'TONE',
  name: 'Wonder',
  slug: 'wonder',
  description: 'Awe at the impossible.',
  example: 'The light bent around her hand like water.',
  sort_order: 1,
  suggested_distinctions: [{ id: 10, name: 'Keen Senses' }],
};

const CATALOG: GlimpseTagOption[] = [TONE_WONDER];

const DRAFT_DISTINCTION: DraftDistinctionEntry = {
  distinction_id: 10,
  distinction_name: 'Keen Senses',
  distinction_slug: 'keen-senses',
  category_slug: 'advantages',
  rank: 1,
  cost: 2,
  notes: '',
};

function renderSection(draft: CharacterDraft) {
  const queryClient = createTestQueryClient();
  seedQueryData(queryClient, characterCreationKeys.glimpseTags(), CATALOG);
  seedQueryData(queryClient, distinctionKeys.draftDistinctions(draft.id), [DRAFT_DISTINCTION]);
  const glimpseProseField = {
    name: 'glimpse_story' as const,
    onChange: vi.fn(),
    onBlur: vi.fn(),
    ref: vi.fn(),
  };
  const result = renderWithCharacterCreationProviders(
    <GlimpseSection draft={draft} glimpseProseField={glimpseProseField} />,
    { queryClient }
  );
  return { ...result, glimpseProseField };
}

describe('GlimpseSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateDraftMock.mockResolvedValue({});
  });

  it('selecting a tone card PATCHes draft_data.glimpse_tag_ids', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    await user.click(screen.getByText('Wonder'));

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          draft_data: expect.objectContaining({ glimpse_tag_ids: [1] }),
        })
      );
    });
  });

  it('toggling a suggested distinction PATCHes glimpse_linked_distinction_ids', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [1] } });
    renderSection(draft);

    // "Keen Senses" is both a Tone-suggested distinction and (because it's
    // also the draft's already-chosen distinction) listed in the manual-link
    // fallback below — either badge toggles the same distinction id.
    await user.click(screen.getAllByText('Keen Senses')[0]);

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          draft_data: expect.objectContaining({ glimpse_linked_distinction_ids: [10] }),
        })
      );
    });
  });

  it('registers the prose textarea under glimpse_story via the passed-down field', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      id: 1,
      draft_data: { glimpse_story: 'Once, in the dark' },
    });
    const { glimpseProseField } = renderSection(draft);

    const textarea = screen.getByLabelText('Your Story') as HTMLTextAreaElement;
    expect(textarea.value).toBe('Once, in the dark');

    await user.type(textarea, '!');

    expect(glimpseProseField.onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        target: expect.objectContaining({ name: 'glimpse_story' }),
      })
    );
  });

  it('renders GlimpseFlow default heading when no heading prop is passed', () => {
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    expect(screen.getByText('The Glimpse')).toBeInTheDocument();
  });

  it('passes a staff-authored heading through to GlimpseFlow', () => {
    const draft = createMockDraft({ id: 1, draft_data: {} });
    const queryClient = createTestQueryClient();
    seedQueryData(queryClient, characterCreationKeys.glimpseTags(), CATALOG);
    seedQueryData(queryClient, distinctionKeys.draftDistinctions(draft.id), [DRAFT_DISTINCTION]);
    const glimpseProseField = {
      name: 'glimpse_story' as const,
      onChange: vi.fn(),
      onBlur: vi.fn(),
      ref: vi.fn(),
    };
    renderWithCharacterCreationProviders(
      <GlimpseSection
        draft={draft}
        glimpseProseField={glimpseProseField}
        heading="A Door You Cannot Unsee"
      />,
      { queryClient }
    );

    expect(screen.getByText('A Door You Cannot Unsee')).toBeInTheDocument();
    expect(screen.queryByText('The Glimpse')).not.toBeInTheDocument();
  });

  it('selects a tag card via the keyboard (Enter)', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    (screen.getByText('Wonder').closest('[role="button"]') as HTMLElement | null)?.focus();
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          draft_data: expect.objectContaining({ glimpse_tag_ids: [1] }),
        })
      );
    });
  });
});
