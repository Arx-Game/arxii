import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThreadedNarrativeReader } from './ThreadedNarrativeReader';
import { loadConversationAnchor } from '../playPreferences';
import { markConversationRead } from '../playQueries';
import type { Interaction } from '@/scenes/types';

vi.mock('../playQueries', () => ({
  markConversationRead: vi.fn().mockResolvedValue({ marked: 0 }),
}));

vi.mock('@/scenes/components/SceneMessages', () => ({
  SceneMessages: ({ filteredInteractions }: { filteredInteractions: Interaction[] }) => (
    <div data-testid="scene-messages">
      {filteredInteractions.map((item) => (
        <p key={item.id}>{item.content}</p>
      ))}
    </div>
  ),
}));

const interaction = (id: number, content: string, thread_id: string): Interaction => ({
  id,
  thread_id,
  persona: { id: id + 10, name: `Writer ${id}` },
  content,
  mode: 'pose',
  visibility: 'default',
  timestamp: `2026-01-01T00:0${id}:00Z`,
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
});

describe('ThreadedNarrativeReader', () => {
  let offsetHeightSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.mocked(markConversationRead).mockClear();
    // Each test uses conversationKey="scene:1" — clear so per-conversation
    // collapse state saved by one test never leaks into the next.
    window.localStorage.clear();

    // jsdom has no layout engine, so every element's offsetHeight is always
    // 0. @tanstack/react-virtual (Chronological branch) reads the scroll
    // container's offsetHeight synchronously — before any ResizeObserver
    // callback, and this repo's ResizeObserver polyfill in src/test/setup.ts
    // is a no-op besides — to decide the visible range; a 0-height container
    // makes it conclude nothing is visible and render zero rows rather than
    // all of them. Stub offsetHeight to a plausible viewport size so the
    // virtualizer computes a real, bounded window in every test.
    offsetHeightSpy = vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(700);
  });

  afterEach(() => {
    offsetHeightSpy.mockRestore();
  });

  it('keeps explicit threads collapsed and exposes keyboard accessible controls', async () => {
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'root', 'thread-a'),
          interaction(2, 'reply', 'thread-a'),
          interaction(3, 'other', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    // thread-b is more recent, so thread-a starts collapsed — expand it first.
    await user.click(screen.getByRole('button', { name: /writer 1.*2 poses/i }));
    expect(screen.getByText('root')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /writer 1.*2 poses/i }));
    expect(screen.queryByText('root')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /writer 1.*2 poses/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  it('collapses all but the most recently active thread by default', () => {
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'older root', 'thread-a'),
          interaction(2, 'newer root', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    // thread-b's timestamp (2026-01-01T00:02:00Z) is later than thread-a's
    // (2026-01-01T00:01:00Z) — it should start expanded, thread-a collapsed.
    expect(screen.getByText('newer root')).toBeInTheDocument();
    expect(screen.queryByText('older root')).not.toBeInTheDocument();
  });

  it("re-derives the default collapse state on a scene change instead of carrying over the previous scene's stale collapsed set", () => {
    // Mirrors GameWindow.tsx's actual mount: `key={sceneFeed.sceneId}` on the
    // same element as `conversationKey={sceneFeed.sceneId}`, so switching
    // scenes forces React to unmount/remount this component (fresh
    // `collapsed`/`storedAnchorState` initializers) rather than reusing one
    // instance across scenes. Without that `key`, the old scene's `collapsed`
    // Set (full of the OLD scene's thread keys) would survive into the new
    // scene, where none of those keys match the new scene's groups — so
    // every thread in the new scene would silently render expanded.
    const { rerender } = render(
      <ThreadedNarrativeReader
        key="scene:1"
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'scene1 older', 'thread-a'),
          interaction(2, 'scene1 newer', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    expect(screen.getByText('scene1 newer')).toBeInTheDocument();
    expect(screen.queryByText('scene1 older')).not.toBeInTheDocument();

    rerender(
      <ThreadedNarrativeReader
        key="scene:2"
        sceneId="2"
        conversationKey="scene:2"
        interactions={[
          interaction(1, 'scene2 older', 'thread-x'),
          interaction(2, 'scene2 newer', 'thread-y'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    expect(screen.getByText('scene2 newer')).toBeInTheDocument();
    expect(screen.queryByText('scene2 older')).not.toBeInTheDocument();
  });

  it('applies the default-collapse-but-most-recent rule once real data arrives after an empty first render', () => {
    // Mirrors a real page load: ThreadedNarrativeReader mounts (same
    // component instance — no `key` change here, unlike the scene-change
    // test above) the instant sceneId becomes truthy, while
    // useSceneInteractions's useInfiniteQuery is still in flight, so
    // `interactions` is `[]` on the very first render. A lazy useState
    // initializer only ever sees that first, empty render and never
    // re-derives the default once real data lands (the bug this test
    // guards against) — the fix instead applies the default via an effect
    // the first time `groups` actually has data.
    const { rerender } = render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[]}
        fetchNextPage={vi.fn()}
      />
    );
    // Empty state: nothing crashes, no group renders.
    expect(screen.getByText('New conversation')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /poses/i })).not.toBeInTheDocument();

    rerender(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'older root', 'thread-a'),
          interaction(2, 'newer root', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    // The newly-arrived data should get the same default-collapse treatment
    // as data present at mount: most-recent thread (thread-b) expanded,
    // the rest (thread-a) collapsed.
    expect(screen.getByText('newer root')).toBeInTheDocument();
    expect(screen.queryByText('older root')).not.toBeInTheDocument();
  });

  it('does not re-apply the default collapse after the user has toggled a thread', async () => {
    // Once the default has been seeded and the user has made their own
    // choice, a later re-render with more groups (e.g. a new pose arriving
    // in a third thread) must not re-run the "collapse all but most recent"
    // logic and stomp the user's manual toggle.
    const user = userEvent.setup();
    const { rerender } = render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'older root', 'thread-a'),
          interaction(2, 'newer root', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    // Expand the default-collapsed thread-a manually.
    await user.click(screen.getByRole('button', { name: /writer 1.*1 pose/i }));
    expect(screen.getByText('older root')).toBeInTheDocument();

    // A new pose arrives in a brand new thread-c.
    rerender(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'older root', 'thread-a'),
          interaction(2, 'newer root', 'thread-b'),
          interaction(3, 'newest root', 'thread-c'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    // The user's manual expand of thread-a must survive — the default-collapse
    // effect is guarded from re-firing after its first seed.
    expect(screen.getByText('older root')).toBeInTheDocument();
  });

  it('chronological mode shows all poses as a flat, time-ordered list', async () => {
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        // Passed out of timestamp order (3, 1, 2) so a component that merely
        // rendered visibleInteractions in prop/array order — never sorting by
        // (timestamp, id) at all — would fail this assertion. interaction(id, ...)
        // derives its timestamp from `id`, so timestamp order here is 1 < 2 < 3
        // (first < second < third) regardless of array position.
        interactions={[
          interaction(3, 'third', 'thread-a'),
          interaction(1, 'first', 'thread-a'),
          interaction(2, 'second', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /chronological/i }));
    const texts = screen.getAllByText(/first|second|third/).map((el) => el.textContent);
    expect(texts).toEqual(['first', 'second', 'third']);
  });

  it('windows a long chronological list instead of mounting every pose', async () => {
    // INITIAL_PAGE_SIZE (20) caps the initially visible slice regardless of
    // windowing, so a naive 300-interaction render would already show fewer
    // than 300 nodes for the wrong reason. Load all of local history first
    // (each click reveals another 20) so the chronological branch actually
    // has all 300 items to render, and the bounded-mount assertion below
    // only passes because of the virtualizer (see the offsetHeight stub in
    // beforeEach above for why that's necessary under jsdom).
    const user = userEvent.setup();
    const many = Array.from({ length: 300 }, (_, i) =>
      interaction(i + 1, `pose ${i + 1}`, 'thread-a')
    );
    const { container } = render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={many}
        fetchNextPage={vi.fn()}
      />
    );
    let loadEarlier = screen.queryByRole('button', { name: /load earlier history/i });
    while (loadEarlier) {
      await user.click(loadEarlier);
      loadEarlier = screen.queryByRole('button', { name: /load earlier history/i });
    }
    await user.click(screen.getByRole('button', { name: /chronological/i }));
    const mountedPoses = container.querySelectorAll('[data-testid="scene-messages"]');
    expect(mountedPoses.length).toBeLessThan(300);
    expect(mountedPoses.length).toBeGreaterThan(0);
  });

  it('persists bulk Expand/Collapse loaded threads clicks, unlike a direct setCollapsed that bypasses saveConversationAnchor', async () => {
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'older root', 'thread-a'),
          interaction(2, 'newer root', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    // thread-a starts collapsed by default (thread-b is more recent).
    await user.click(screen.getByRole('button', { name: /collapse loaded threads/i }));
    expect(loadConversationAnchor('scene:1')?.collapsed.sort()).toEqual(
      ['thread-a', 'thread-b'].sort()
    );

    await user.click(screen.getByRole('button', { name: /expand loaded threads/i }));
    expect(loadConversationAnchor('scene:1')?.collapsed).toEqual([]);
  });

  it('registers every rendered pose with the dwell-tracking observer, in both Threads and Chronological view', async () => {
    // usePoseReadTracking.test.ts already covers the dwell-timer/flush timing
    // math in isolation. This test covers the other half: that
    // ThreadedNarrativeReader actually feeds `observe()` a real element for
    // every rendered pose in BOTH view branches — the wiring the ref
    // collision in Chronological view (Task 10's chronoVirtualizer.measureElement
    // already on the row) could easily have silently dropped.
    const user = userEvent.setup();
    const observedElements: Element[] = [];
    const unobservedElements: Element[] = [];
    class SpyIntersectionObserver {
      observe(element: Element) {
        observedElements.push(element);
      }
      unobserve(element: Element) {
        unobservedElements.push(element);
      }
      disconnect(): void {
        return undefined;
      }
      takeRecords(): IntersectionObserverEntry[] {
        return [];
      }
    }
    vi.stubGlobal('IntersectionObserver', SpyIntersectionObserver);

    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[interaction(1, 'root', 'thread-a'), interaction(2, 'reply', 'thread-a')]}
        fetchNextPage={vi.fn()}
      />
    );
    // Threads view: the single thread is also the most recent, so it starts
    // expanded and both its poses are mounted (and thus observed) already.
    expect(observedElements).toHaveLength(2);

    observedElements.length = 0;
    await user.click(screen.getByRole('button', { name: /chronological/i }));
    // Switching view unmounts the Threads-view wrappers (unobserving them)
    // and mounts the Chronological-view wrappers (observing the new ones) —
    // confirms the Chronological branch's inner PoseReadTarget wrapper
    // reaches the observer independently of chronoVirtualizer.measureElement.
    expect(unobservedElements).toHaveLength(2);
    expect(observedElements).toHaveLength(2);

    vi.unstubAllGlobals();
  });

  it('calls markConversationRead with the current conversation key and the latest visible pose timestamp', async () => {
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'older root', 'thread-a'),
          interaction(2, 'newer root', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );

    await user.click(screen.getByRole('button', { name: /mark conversation read/i }));

    expect(markConversationRead).toHaveBeenCalledTimes(1);
    // interaction(id, ...) derives timestamp `2026-01-01T00:0{id}:00Z` from id,
    // so the later pose (id 2) carries the latest timestamp of the two.
    expect(markConversationRead).toHaveBeenCalledWith('scene:1', '2026-01-01T00:02:00Z');
  });
});
