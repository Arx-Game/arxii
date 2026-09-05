/**
 * Landing page (Gatefold) query hook tests (#3305).
 *
 * Fetchers are mocked (`vi.mock('../api', ...)`) — these tests exercise the
 * composition/wiring in queries.ts, not the network layer.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { createElement } from 'react';
import {
  firstOfMonthISO,
  useFeaturedLore,
  useMonthlySceneCount,
  usePublicBeginnings,
  usePublicStartingAreas,
  useSceneExcerpt,
} from '../queries';
import type { Beginnings, StartingArea } from '@/character-creation/types';
import type { CodexEntryListItem } from '@/codex/types';
import type { Interaction, SceneListItem } from '@/scenes/types';

vi.mock('../api', () => ({
  getPublicStartingAreas: vi.fn(),
  getPublicBeginnings: vi.fn(),
  getScenesSpotlight: vi.fn(),
  getSceneInteractions: vi.fn(),
  getCompletedSceneCount: vi.fn(),
}));

vi.mock('@/codex/api', () => ({
  getFeaturedEntries: vi.fn(),
}));

import * as api from '../api';
import * as codexApi from '@/codex/api';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const mockStartingArea: StartingArea = {
  id: 1,
  name: 'Arx',
  description: 'The city itself.',
  crest_image: null,
  is_accessible: true,
  realm_theme: 'default',
};

const mockBeginnings: Beginnings = {
  id: 1,
  name: 'Noble Birth',
  description: 'Born to a great house.',
  art_image: null,
  allowed_species_ids: [],
  grants_species_languages: true,
  cg_point_cost: 0,
  is_accessible: true,
  codex_entry_ids: [],
};

function makeScene(overrides: Partial<SceneListItem> = {}): SceneListItem {
  return {
    id: 1,
    name: 'An Evening at the Rose Garden',
    description: '',
    date_started: '2026-08-01T20:00:00Z',
    location: { id: 1, name: 'The Rose Garden' },
    participants: [],
    ...overrides,
  };
}

function makePose(overrides: Partial<Interaction> = {}): Interaction {
  return {
    id: 1,
    persona: { id: 1, name: 'Someone' },
    content: 'poses quietly.',
    mode: 'pose',
    visibility: 'default',
    timestamp: '2026-08-01T20:05:00Z',
    scene: 1,
    reactions: [],
    is_favorited: false,
    place: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
    pose_kind: 'standard',
    endorsee_sheet_id: null,
    endorsable_resonances: [],
    pose_endorsers: [],
    my_pose_endorsement: null,
    entry_endorsers: [],
    entry_endorsed_by_me: false,
    ...overrides,
  };
}

describe('home query hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('usePublicStartingAreas', () => {
    it('fetches starting areas', async () => {
      vi.mocked(api.getPublicStartingAreas).mockResolvedValue([mockStartingArea]);

      const { result } = renderHook(() => usePublicStartingAreas(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual([mockStartingArea]);
    });
  });

  describe('usePublicBeginnings', () => {
    it('is disabled until a starting area id is passed', () => {
      const { result } = renderHook(() => usePublicBeginnings(undefined), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
      expect(api.getPublicBeginnings).not.toHaveBeenCalled();
    });

    it('fetches beginnings for the given starting area once enabled', async () => {
      vi.mocked(api.getPublicBeginnings).mockResolvedValue([mockBeginnings]);

      const { result } = renderHook(() => usePublicBeginnings(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual([mockBeginnings]);
      expect(api.getPublicBeginnings).toHaveBeenCalledWith(1);
    });
  });

  describe('useSceneExcerpt', () => {
    it('walks past a scene with zero visible poses to the next', async () => {
      const emptyScene = makeScene({ id: 1, name: 'Empty Scene' });
      const liveScene = makeScene({ id: 2, name: 'Live Scene' });
      const pose = makePose({ id: 10, scene: 2 });

      vi.mocked(api.getScenesSpotlight).mockResolvedValue({
        in_progress: [],
        recent: [emptyScene, liveScene],
      });
      vi.mocked(api.getSceneInteractions).mockImplementation(async (sceneId: number) =>
        sceneId === liveScene.id ? [pose] : []
      );

      const { result } = renderHook(() => useSceneExcerpt(), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toEqual({ scene: liveScene, poses: [pose] });
      expect(api.getSceneInteractions).toHaveBeenNthCalledWith(1, emptyScene.id);
      expect(api.getSceneInteractions).toHaveBeenNthCalledWith(2, liveScene.id);
    });

    it('resolves null when all candidates are empty, capping the walk at 3', async () => {
      const scenes = [
        makeScene({ id: 1 }),
        makeScene({ id: 2 }),
        makeScene({ id: 3 }),
        makeScene({ id: 4 }),
      ];

      vi.mocked(api.getScenesSpotlight).mockResolvedValue({
        in_progress: [],
        recent: scenes,
      });
      vi.mocked(api.getSceneInteractions).mockResolvedValue([]);

      const { result } = renderHook(() => useSceneExcerpt(), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBeNull();
      // Only the first 3 candidates are tried, bounding the request count.
      expect(api.getSceneInteractions).toHaveBeenCalledTimes(3);
      expect(api.getSceneInteractions).not.toHaveBeenCalledWith(4);
    });
  });

  describe('firstOfMonthISO', () => {
    it('resolves local midnight on the 1st of the given date', () => {
      const iso = firstOfMonthISO(new Date(2026, 7, 22, 15, 30));
      const parsed = new Date(iso);

      expect(parsed.getFullYear()).toBe(2026);
      expect(parsed.getMonth()).toBe(7);
      expect(parsed.getDate()).toBe(1);
      expect(parsed.getHours()).toBe(0);
      expect(parsed.getMinutes()).toBe(0);
    });
  });

  describe('useMonthlySceneCount', () => {
    it('passes a first-of-month finished_after param', async () => {
      vi.mocked(api.getCompletedSceneCount).mockResolvedValue(14);

      const { result } = renderHook(() => useMonthlySceneCount(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toBe(14);
      expect(api.getCompletedSceneCount).toHaveBeenCalledWith(firstOfMonthISO());
    });
  });

  describe('useFeaturedLore', () => {
    const mockEntry: CodexEntryListItem = {
      id: 10,
      name: 'The Shroud',
      summary: 'A grey veil no army and no messenger ever crossed.',
      is_public: true,
      is_featured: true,
      featured_order: 1,
      subject: 1,
      subject_name: 'The World',
      subject_path: [],
      display_order: 1,
      knowledge_status: null,
      known_by: [],
      art_url: null,
      perspective_of: null,
      also_filed_under: [],
    };

    it('fetches featured codex entries', async () => {
      vi.mocked(codexApi.getFeaturedEntries).mockResolvedValue([mockEntry]);

      const { result } = renderHook(() => useFeaturedLore(), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual([mockEntry]);
    });

    it('resolves quietly (no throw) when the fetch fails — no throwOnError on this page', async () => {
      vi.mocked(codexApi.getFeaturedEntries).mockRejectedValue(new Error('boom'));

      const { result } = renderHook(() => useFeaturedLore(), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.data).toBeUndefined();
    });
  });
});
