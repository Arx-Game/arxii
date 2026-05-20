/**
 * Stories Authoring API + Query Hooks Tests (Task D2)
 *
 * Covers the authoring data layer: episode maturity promotion, story
 * scope assignment, and OOC StoryNote read/create. Mirrors the Vitest +
 * React Query wrapper pattern in queries.test.tsx exactly.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import {
  storiesKeys,
  useAssignStory,
  useCreateStoryNote,
  usePromoteEpisode,
  useStoryNotes,
} from '../queries';

// Mock the API module
vi.mock('../api', () => ({
  promoteEpisode: vi.fn(),
  assignStory: vi.fn(),
  listStoryNotes: vi.fn(),
  createStoryNote: vi.fn(),
}));

import * as api from '../api';
import { assignStory, createStoryNote, listStoryNotes, promoteEpisode } from '../api';

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
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Fixture data
// ---------------------------------------------------------------------------

const mockEpisode = {
  id: 20,
  chapter: 'Chapter One',
  title: 'The Arrival',
  description: 'They arrive.',
  order: 1,
  is_active: true,
  summary: 'Beat summary.',
  maturity: 'outline' as const,
  resting_conclusion: '',
  is_ending: false,
  consequences: '',
  completed_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
};

const mockStory = {
  id: 1,
  title: 'A tale of two cities',
  description: 'A story of revolution.',
  status: 'active' as const,
  privacy: 'private' as const,
  scope: 'character' as const,
  owners: ['player1'],
  active_gms: [],
  trust_requirements: '',
  character_sheet: 42,
  chapters_count: 2,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
  completed_at: null,
  primary_table: null,
};

const mockStoryNote = {
  id: 7,
  story: 1,
  author_account: 3,
  body: 'Remember to foreshadow the betrayal.',
  created_at: '2026-04-19T11:00:00Z',
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Stories Authoring Hooks (D2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // storiesKeys factory addition
  // -------------------------------------------------------------------------
  describe('storiesKeys.storyNotes', () => {
    it('generates the story-notes list key', () => {
      expect(storiesKeys.storyNotes(1)).toEqual(['stories', 'story-notes', 1]);
    });
  });

  // -------------------------------------------------------------------------
  // api: promoteEpisode
  // -------------------------------------------------------------------------
  describe('promoteEpisode', () => {
    it('POSTs to /api/episodes/{id}/promote/ and returns the episode', async () => {
      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(mockEpisode), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const { promoteEpisode: realPromoteEpisode } =
        await vi.importActual<typeof import('../api')>('../api');

      const result = await realPromoteEpisode(20, { target: 'plot' });

      expect(fetchSpy).toHaveBeenCalled();
      const [url, init] = fetchSpy.mock.calls[0];
      expect(String(url)).toContain('/api/episodes/20/promote/');
      expect(init?.method).toBe('POST');
      expect(JSON.parse(String(init?.body))).toEqual({ target: 'plot' });
      expect(result).toEqual(mockEpisode);

      fetchSpy.mockRestore();
    });

    it('attaches the failed Response to the thrown error on a non-ok response', async () => {
      // Drives the REAL api.promoteEpisode through a 400 to prove the
      // api->component error seam: PromoteMaturityButton.handleError reads
      // `'response' in err` then `response.json()`. Locks the real contract,
      // not a fabricated `{ response }`.
      const errorBody = { target: 'Promotion to PLOT requires a resting conclusion.' };
      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(errorBody), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const { promoteEpisode: realPromoteEpisode } =
        await vi.importActual<typeof import('../api')>('../api');

      let caught: unknown;
      try {
        await realPromoteEpisode(20, { target: 'plot' });
      } catch (err) {
        caught = err;
      }

      expect(caught).toBeInstanceOf(Error);
      expect(caught && typeof caught === 'object' && 'response' in caught).toBe(true);
      const response = (caught as { response?: Response }).response;
      expect(response).toBeInstanceOf(Response);
      await expect(response?.json()).resolves.toEqual(errorBody);

      fetchSpy.mockRestore();
    });
  });

  // -------------------------------------------------------------------------
  // api: assignStory
  // -------------------------------------------------------------------------
  describe('assignStory', () => {
    it('POSTs to /api/stories/{id}/assign-to-scope/', async () => {
      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(mockStory), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const { assignStory: realAssignStory } =
        await vi.importActual<typeof import('../api')>('../api');

      const result = await realAssignStory(1, { scope: 'character', character_sheet: 42 });

      const [url, init] = fetchSpy.mock.calls[0];
      expect(String(url)).toContain('/api/stories/1/assign-to-scope/');
      expect(init?.method).toBe('POST');
      expect(JSON.parse(String(init?.body))).toEqual({
        scope: 'character',
        character_sheet: 42,
      });
      expect(result).toEqual(mockStory);

      fetchSpy.mockRestore();
    });

    it('attaches the failed Response to the thrown error on a non-ok response', async () => {
      // Drives the REAL api.assignStory through a 400 to prove the
      // api->component error seam: ScopeAssignDialog.handleError reads
      // `'response' in err` then `response.json()`. Locks the real contract,
      // not a fabricated `{ response }`.
      const errorBody = {
        scope: 'This story is already assigned to a scope and cannot be re-assigned.',
      };
      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(errorBody), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const { assignStory: realAssignStory } =
        await vi.importActual<typeof import('../api')>('../api');

      let caught: unknown;
      try {
        await realAssignStory(1, { scope: 'character', character_sheet: 42 });
      } catch (err) {
        caught = err;
      }

      expect(caught).toBeInstanceOf(Error);
      expect(caught && typeof caught === 'object' && 'response' in caught).toBe(true);
      const response = (caught as { response?: Response }).response;
      expect(response).toBeInstanceOf(Response);
      await expect(response?.json()).resolves.toEqual(errorBody);

      fetchSpy.mockRestore();
    });
  });

  // -------------------------------------------------------------------------
  // api: markBeat (ledger I-A twin)
  // -------------------------------------------------------------------------
  describe('markBeat', () => {
    it('attaches the failed Response to the thrown error on a non-ok response', async () => {
      // Drives the REAL api.markBeat through a 400 to prove the
      // api->component error seam: MarkBeatDialog.onError reads
      // `'response' in err` then `response.json()` to surface DRF field
      // errors. Without the fix markBeat threw a plain Error (no
      // `.response`) so that branch was dead. Locks the real contract.
      const errorBody = { gm_notes: ['This field is required.'] };
      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(errorBody), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const { markBeat: realMarkBeat } = await vi.importActual<typeof import('../api')>('../api');

      let caught: unknown;
      try {
        await realMarkBeat(11, { outcome: 'success' });
      } catch (err) {
        caught = err;
      }

      expect(caught).toBeInstanceOf(Error);
      expect(caught && typeof caught === 'object' && 'response' in caught).toBe(true);
      const response = (caught as { response?: Response }).response;
      expect(response).toBeInstanceOf(Response);
      await expect(response?.json()).resolves.toEqual(errorBody);

      fetchSpy.mockRestore();
    });
  });

  // -------------------------------------------------------------------------
  // api: listStoryNotes
  // -------------------------------------------------------------------------
  describe('listStoryNotes', () => {
    it('GETs /api/story-notes/?story=...', async () => {
      const paginated = { count: 1, next: null, previous: null, results: [mockStoryNote] };
      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(paginated), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const { listStoryNotes: realListStoryNotes } =
        await vi.importActual<typeof import('../api')>('../api');

      const result = await realListStoryNotes({ story: 1 });

      const [url, init] = fetchSpy.mock.calls[0];
      expect(String(url)).toContain('/api/story-notes/?story=1');
      expect(init?.method ?? 'GET').toBe('GET');
      expect(result.results).toHaveLength(1);
      expect(result.results[0].body).toBe('Remember to foreshadow the betrayal.');

      fetchSpy.mockRestore();
    });
  });

  // -------------------------------------------------------------------------
  // api: createStoryNote
  // -------------------------------------------------------------------------
  describe('createStoryNote', () => {
    it('POSTs /api/story-notes/', async () => {
      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(mockStoryNote), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        })
      );

      const { createStoryNote: realCreateStoryNote } =
        await vi.importActual<typeof import('../api')>('../api');

      const result = await realCreateStoryNote({
        story: 1,
        body: 'Remember to foreshadow the betrayal.',
      });

      const [url, init] = fetchSpy.mock.calls[0];
      expect(String(url)).toContain('/api/story-notes/');
      expect(init?.method).toBe('POST');
      expect(JSON.parse(String(init?.body))).toEqual({
        story: 1,
        body: 'Remember to foreshadow the betrayal.',
      });
      expect(result).toEqual(mockStoryNote);

      fetchSpy.mockRestore();
    });
  });

  // -------------------------------------------------------------------------
  // usePromoteEpisode
  // -------------------------------------------------------------------------
  describe('usePromoteEpisode', () => {
    it('calls promoteEpisode and invalidates episode + story-related keys', async () => {
      vi.mocked(promoteEpisode).mockResolvedValue(mockEpisode);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );

      const { result } = renderHook(() => usePromoteEpisode(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          episodeId: 20,
          storyId: 5,
          target: 'plot',
        });
      });

      expect(api.promoteEpisode).toHaveBeenCalledWith(20, { target: 'plot' });
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.episode(20) })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.episodeList() })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.story(5) })
      );
    });
  });

  // -------------------------------------------------------------------------
  // useAssignStory
  // -------------------------------------------------------------------------
  describe('useAssignStory', () => {
    it('calls assignStory and invalidates story + list + dashboards', async () => {
      vi.mocked(assignStory).mockResolvedValue(mockStory);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );

      const { result } = renderHook(() => useAssignStory(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          storyId: 1,
          scope: 'character',
          character_sheet: 42,
        });
      });

      expect(api.assignStory).toHaveBeenCalledWith(1, {
        scope: 'character',
        character_sheet: 42,
      });
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.story(1) })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.storyList() })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.myActive() })
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.gmQueue() })
      );
    });
  });

  // -------------------------------------------------------------------------
  // useStoryNotes
  // -------------------------------------------------------------------------
  describe('useStoryNotes', () => {
    it('fetches story notes for a story', async () => {
      const paginated = { count: 1, next: null, previous: null, results: [mockStoryNote] };
      vi.mocked(listStoryNotes).mockResolvedValue(paginated);

      const { result } = renderHook(() => useStoryNotes(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.results).toHaveLength(1);
      expect(result.current.data?.results[0].body).toBe('Remember to foreshadow the betrayal.');
      expect(api.listStoryNotes).toHaveBeenCalledWith({ story: 1 });
    });
  });

  // -------------------------------------------------------------------------
  // useCreateStoryNote
  // -------------------------------------------------------------------------
  describe('useCreateStoryNote', () => {
    it('calls createStoryNote and invalidates the story-notes list for that story', async () => {
      vi.mocked(createStoryNote).mockResolvedValue(mockStoryNote);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );

      const { result } = renderHook(() => useCreateStoryNote(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          story: 1,
          body: 'Remember to foreshadow the betrayal.',
        });
      });

      expect(api.createStoryNote).toHaveBeenCalledWith({
        story: 1,
        body: 'Remember to foreshadow the betrayal.',
      });
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: storiesKeys.storyNotes(1) })
      );
    });
  });
});
