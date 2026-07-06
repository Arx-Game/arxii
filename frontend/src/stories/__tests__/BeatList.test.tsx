/**
 * BeatList Tests (#1853)
 *
 * Covers the query→map→prop wiring between useMyPendingTreasuredSignoffs and
 * BeatRow's pendingSignoffSubjectIds prop:
 *  - a beat with a matching pending-signoff entry gets that entry's subject
 *    ids forwarded to its BeatRow
 *  - a beat with no matching entry gets undefined (no false-positive prompt)
 *  - when tenureId is not provided, useMyPendingTreasuredSignoffs is called
 *    with an empty array (the query is skipped)
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { BeatList } from '../components/BeatList';
import type { Beat } from '../types';

vi.mock('../queries', () => ({
  useBeatList: vi.fn(),
  useAggregateBeatContributions: vi.fn(),
}));

vi.mock('@/boundaries/queries', () => ({
  useMyPendingTreasuredSignoffs: vi.fn(),
}));

vi.mock('../components/BeatRow', () => ({
  BeatRow: ({
    beat,
    pendingSignoffSubjectIds,
  }: {
    beat: Beat;
    pendingSignoffSubjectIds?: number[];
  }) => (
    <li
      data-testid={`beat-row-${beat.id}`}
      data-pending-subject-ids={JSON.stringify(pendingSignoffSubjectIds)}
    />
  ),
}));

import * as storiesQueries from '../queries';
import * as boundariesQueries from '@/boundaries/queries';

function makeBeat(overrides: Partial<Beat> = {}): Beat {
  return {
    id: 1,
    episode: 10,
    episode_title: 'Test Episode',
    chapter_title: 'Test Chapter',
    story_id: 5,
    story_title: 'Test Story',
    predicate_type: 'gm_marked',
    outcome: 'unsatisfied',
    visibility: 'hinted',
    internal_description: 'The villain confronts the hero',
    player_hint: 'Confront the villain',
    player_resolution_text: undefined,
    order: 1,
    required_level: undefined,
    required_achievement: undefined,
    required_condition_template: undefined,
    required_codex_entry: undefined,
    referenced_story: undefined,
    referenced_milestone_type: undefined,
    referenced_chapter: undefined,
    referenced_episode: undefined,
    required_points: undefined,
    agm_eligible: false,
    deadline: undefined,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
    can_mark: false,
    ...overrides,
  };
}

function mockBeatList(beats: Beat[]) {
  vi.mocked(storiesQueries.useBeatList).mockReturnValue({
    data: { count: beats.length, next: null, previous: null, results: beats },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof storiesQueries.useBeatList>);

  vi.mocked(storiesQueries.useAggregateBeatContributions).mockReturnValue({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof storiesQueries.useAggregateBeatContributions>);
}

describe('BeatList — pending sign-off query-to-prop wiring (#1853)', () => {
  it('forwards a matching entry treasured_subject_ids to the corresponding BeatRow', () => {
    const beatWithPending = makeBeat({ id: 1 });
    const beatWithoutPending = makeBeat({ id: 2 });
    mockBeatList([beatWithPending, beatWithoutPending]);

    vi.mocked(boundariesQueries.useMyPendingTreasuredSignoffs).mockReturnValue({
      data: [{ beat_id: 1, treasured_subject_ids: [100, 200] }],
      isLoading: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof boundariesQueries.useMyPendingTreasuredSignoffs>);

    renderWithProviders(<BeatList episodeId={10} tenureId={7} />);

    expect(screen.getByTestId('beat-row-1')).toHaveAttribute(
      'data-pending-subject-ids',
      JSON.stringify([100, 200])
    );
  });

  it('leaves pendingSignoffSubjectIds undefined for a beat with no matching entry', () => {
    const beatWithPending = makeBeat({ id: 1 });
    const beatWithoutPending = makeBeat({ id: 2 });
    mockBeatList([beatWithPending, beatWithoutPending]);

    vi.mocked(boundariesQueries.useMyPendingTreasuredSignoffs).mockReturnValue({
      data: [{ beat_id: 1, treasured_subject_ids: [100, 200] }],
      isLoading: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof boundariesQueries.useMyPendingTreasuredSignoffs>);

    renderWithProviders(<BeatList episodeId={10} tenureId={7} />);

    // JSON.stringify(undefined) is itself undefined, so the mock BeatRow
    // never applies the attribute at all when there's no matching entry.
    expect(screen.getByTestId('beat-row-2')).not.toHaveAttribute('data-pending-subject-ids');
  });

  it('calls useMyPendingTreasuredSignoffs with an empty array when tenureId is not provided', () => {
    mockBeatList([makeBeat({ id: 1 }), makeBeat({ id: 2 })]);

    vi.mocked(boundariesQueries.useMyPendingTreasuredSignoffs).mockReturnValue({
      data: undefined,
      isLoading: false,
      isSuccess: false,
      error: null,
    } as unknown as ReturnType<typeof boundariesQueries.useMyPendingTreasuredSignoffs>);

    renderWithProviders(<BeatList episodeId={10} />);

    expect(boundariesQueries.useMyPendingTreasuredSignoffs).toHaveBeenCalledWith([]);
  });
});
