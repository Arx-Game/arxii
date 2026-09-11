import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThreadedNarrativeReader } from './ThreadedNarrativeReader';
import {
  DEFAULT_PLAY_PREFERENCES,
  loadConversationAnchor,
  saveConversationAnchor,
  savePlayPreferences,
  usePlayPreferences,
} from '../playPreferences';
import { markConversationRead } from '../playQueries';
import type { Interaction } from '@/scenes/types';

vi.mock('../playQueries', () => ({
  markConversationRead: vi.fn().mockResolvedValue({ marked: 0 }),
}));

// jsdom has no Element.prototype.scrollTo -- @tanstack/react-virtual's
// scrollToIndex (used by the Chronological-view anchor restore) calls it
// internally to move the scroll container, and its default `elementScroll`
// implementation calls it via optional chaining, so without this stub the
// call is silently a no-op and restoration would be unobservable here (not
// merely imprecise). Mirrors the existing scrollIntoView stub in
// src/test/setup.ts for the same class of jsdom gap.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = function (this: HTMLElement, optionsOrX?: ScrollToOptions | number) {
    if (typeof optionsOrX === 'object' && optionsOrX !== null && 'top' in optionsOrX) {
      this.scrollTop = optionsOrX.top ?? this.scrollTop;
    }
  } as typeof Element.prototype.scrollTo;
}

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

// Anchor save/restore (#3759 Wave 6) locates poses via `getBoundingClientRect`
// and locates its scroll container via `scrollHeight > clientHeight` — none
// of which jsdom computes from real layout. `poseOffsets` maps a pose id to
// the `top` its element's getBoundingClientRect should report (relative to a
// containerTop of 0, since the container itself never carries a
// `data-pose-id` and so always falls through to offset 0 below); each test
// sets it before rendering/scrolling to simulate a specific on-screen layout.
let poseOffsets: Record<string, number> = {};

describe('ThreadedNarrativeReader', () => {
  let offsetHeightSpy: ReturnType<typeof vi.spyOn>;
  let scrollHeightSpy: ReturnType<typeof vi.spyOn>;
  let clientHeightSpy: ReturnType<typeof vi.spyOn>;
  let rectSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.mocked(markConversationRead).mockClear();
    // Each test uses conversationKey="scene:1" — clear so per-conversation
    // collapse state saved by one test never leaks into the next.
    window.localStorage.clear();
    poseOffsets = {};

    // jsdom has no layout engine, so every element's offsetHeight is always
    // 0. @tanstack/react-virtual (Chronological branch) reads the scroll
    // container's offsetHeight synchronously — before any ResizeObserver
    // callback, and this repo's ResizeObserver polyfill in src/test/setup.ts
    // is a no-op besides — to decide the visible range; a 0-height container
    // makes it conclude nothing is visible and render zero rows rather than
    // all of them. Stub offsetHeight to a plausible viewport size so the
    // virtualizer computes a real, bounded window in every test.
    offsetHeightSpy = vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(700);

    // findScrollContainer (#3759 Wave 6) walks up from the reader's own root
    // looking for the first ancestor whose content overflows. Stubbing this
    // globally to always be true makes the reader's own outermost div (the
    // first node checked) resolve as "the container" in every test — exactly
    // mirroring GameWindow.tsx's real `feedScrollRef` div in production,
    // without needing an extra wrapper element here.
    scrollHeightSpy = vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(2000);
    clientHeightSpy = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(700);
    rectSpy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: HTMLElement
    ) {
      const poseId = this.dataset?.poseId;
      const top = poseId !== undefined ? (poseOffsets[poseId] ?? 0) : 0;
      return {
        top,
        bottom: top,
        left: 0,
        right: 0,
        width: 0,
        height: 0,
        x: 0,
        y: top,
        toJSON() {
          return this;
        },
      } as DOMRect;
    });
  });

  afterEach(() => {
    offsetHeightSpy.mockRestore();
    scrollHeightSpy.mockRestore();
    clientHeightSpy.mockRestore();
    rectSpy.mockRestore();
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

  describe('reading-position anchors (#3759 Wave 6)', () => {
    it('does not save an anchor synchronously on scroll -- only after the debounce settles', async () => {
      poseOffsets = { 1: -50, 2: 100 };
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );

      fireEvent.scroll(screen.getByLabelText('Story reader'));
      // Immediately after the scroll event, nothing has been persisted yet —
      // a naive "save on every tick" implementation would already have
      // written here. Nothing has ever been saved for this conversation, so
      // the whole stored entry is absent (`null`), not merely an `anchor` of
      // `null` inside a present entry.
      expect(loadConversationAnchor('scene:1')).toBeNull();

      await new Promise((resolve) => setTimeout(resolve, 350));
      expect(loadConversationAnchor('scene:1')?.anchor).toEqual({
        poseId: '1',
        threadId: 'thread-a',
        offsetPx: -50,
      });
    });

    it('saves the pose currently at the top of the viewport, not just any visible pose', async () => {
      // pose 1 has scrolled just above the container's top edge (top <= 0);
      // pose 2 is further down, still fully below the top. The topmost-
      // visible algorithm must pick pose 1 (the one "in charge" of the top),
      // not pose 2 merely because it's also on screen.
      poseOffsets = { 1: -12, 2: 340 };
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );

      fireEvent.scroll(screen.getByLabelText('Story reader'));
      await new Promise((resolve) => setTimeout(resolve, 350));

      expect(loadConversationAnchor('scene:1')?.anchor).toEqual({
        poseId: '1',
        threadId: 'thread-a',
        offsetPx: -12,
      });
    });

    it('preserves the collapsed-thread list already being persisted when a scroll save fires', async () => {
      // Both poses must stay rendered for the scroll-save to find a topmost
      // pose at all -- "Collapse loaded threads" would hide everything
      // (including thread-b, already expanded by the recency default) and
      // trivially pass by never saving anything, so this expands the
      // default-collapsed thread-a instead, leaving thread-b collapsed.
      poseOffsets = { 1: 20, 2: 200 };
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
      // thread-b (more recent) starts expanded; thread-a starts collapsed.
      await user.click(screen.getByRole('button', { name: /writer 1.*1 pose/i }));
      expect(loadConversationAnchor('scene:1')?.collapsed).toEqual([]);
      expect(screen.getByText('older root')).toBeInTheDocument();
      expect(screen.getByText('newer root')).toBeInTheDocument();

      fireEvent.scroll(screen.getByLabelText('Story reader'));
      await new Promise((resolve) => setTimeout(resolve, 350));

      const stored = loadConversationAnchor('scene:1');
      expect(stored?.anchor).not.toBeNull();
      // The collapse-toggle's own persisted list must survive the anchor
      // save (a stale-`storedAnchorState`-style regression would instead
      // have reverted `collapsed` to whatever it was at mount).
      expect(stored?.collapsed).toEqual([]);
    });

    it('restores scroll position to the anchored pose once real data has arrived (mirrors the default-collapse async-arrival timing fix)', () => {
      saveConversationAnchor('scene:1', {
        anchor: { poseId: '2', threadId: 'thread-a', offsetPx: 40 },
        collapsed: [],
      });
      const { rerender } = render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[]}
          fetchNextPage={vi.fn()}
        />
      );
      const root = screen.getByLabelText('Story reader');
      // No poses rendered yet — nothing to restore into, and nothing throws.
      expect(root.scrollTop).toBe(0);

      poseOffsets = { 2: 300 };
      rerender(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );

      // scrollTop += (pose 2's current top, 300) - (its recorded offset, 40).
      expect(root.scrollTop).toBe(260);
    });

    it("falls back to the reader's default position when the anchored pose is not in the currently loaded set", () => {
      saveConversationAnchor('scene:1', {
        anchor: { poseId: '999', threadId: 'thread-z', offsetPx: 40 },
        collapsed: [],
      });
      poseOffsets = { 1: 0 };
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[interaction(1, 'first', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );

      // Best-effort: pose 999 (e.g. on an older, not-yet-fetched history
      // page) isn't found, so nothing crashes and scrollTop is left alone.
      expect(screen.getByLabelText('Story reader').scrollTop).toBe(0);
      expect(screen.getByText('first')).toBeInTheDocument();
    });

    it('never persists an anchor while reading in read-only (historical reference) mode', async () => {
      poseOffsets = { 1: -30, 2: 60 };
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
          readOnly
        />
      );

      fireEvent.scroll(screen.getByLabelText('Story reader'));
      await new Promise((resolve) => setTimeout(resolve, 350));

      // Nothing was ever saved for this conversation, so the whole stored
      // entry is absent.
      expect(loadConversationAnchor('scene:1')).toBeNull();
    });

    it('does not restore into a read-only (historical reference) view on mount', () => {
      saveConversationAnchor('scene:1', {
        anchor: { poseId: '2', threadId: 'thread-a', offsetPx: 40 },
        collapsed: [],
      });
      poseOffsets = { 2: 300 };
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
          readOnly
        />
      );

      expect(screen.getByLabelText('Story reader').scrollTop).toBe(0);
    });

    it('restores the prior live anchor when readOnly flips back to false (Return to live, Decision #5)', () => {
      saveConversationAnchor('scene:1', {
        anchor: { poseId: '2', threadId: 'thread-a', offsetPx: 40 },
        collapsed: [],
      });
      const props = (readOnly: boolean) => (
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
          readOnly={readOnly}
        />
      );

      poseOffsets = { 2: 40 };
      const { rerender } = render(props(false));
      const root = screen.getByLabelText('Story reader');
      // Live mount: pose 2 is already sitting exactly at its recorded offset.
      expect(root.scrollTop).toBe(0);

      // Enter a historical reference on the SAME component instance (as
      // GameWindow.tsx does when the reference targets the same scene) —
      // mirrors a cached reference that never shows a loading interstitial,
      // so this is the same mounted instance the whole way through.
      rerender(props(true));

      // Layout shifted while away (e.g. new poses arrived live in the
      // background) — pose 2 now sits further down.
      poseOffsets = { 2: 300 };
      rerender(props(false));

      // Restored again on the readOnly:true -> false transition, even
      // though the reader's one-shot initial-mount restore already ran
      // above — proving this is the explicit return-to-live re-anchor, not
      // just the initial seed re-firing.
      expect(root.scrollTop).toBe(260);
    });

    it('keeps the anchored pose in the same relative position after a prose-size/measure preference change (font/measure survival, Acceptance A08)', () => {
      saveConversationAnchor('scene:1', {
        anchor: { poseId: '2', threadId: 'thread-a', offsetPx: 40 },
        collapsed: [],
      });
      poseOffsets = { 2: 40 };
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );
      const root = screen.getByLabelText('Story reader');
      expect(root.scrollTop).toBe(0);

      // A font-size change made elsewhere (DisplaySettings.tsx) is a second,
      // independent usePlayPreferences() consumer — the two only observe
      // each other through the shared external store (#3759 Wave 6
      // playPreferences.ts fix; a plain per-instance useState would leave
      // the reader's own `preferences.proseSize` stale forever).
      const otherInstance = renderHook(() => usePlayPreferences());
      // The larger font reflows everything below pose 1, moving pose 2
      // further down the page.
      poseOffsets = { 2: 220 };
      act(() => {
        otherInstance.result.current.update({ proseSize: 18 });
      });

      // Re-anchored: scrollTop += (pose 2's new top, 220) - (its recorded
      // offset, 40) — the same pose stays at the same relative position.
      expect(root.scrollTop).toBe(180);
    });

    it('debounces anchor saves in Chronological view too, using its own virtualized scroll container', async () => {
      poseOffsets = { 1: -40, 2: 90 };
      const user = userEvent.setup();
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );
      await user.click(screen.getByRole('button', { name: /chronological/i }));

      fireEvent.scroll(screen.getByTestId('chrono-scroll-container'));
      expect(loadConversationAnchor('scene:1')).toBeNull();

      await new Promise((resolve) => setTimeout(resolve, 350));
      expect(loadConversationAnchor('scene:1')?.anchor).toEqual({
        poseId: '1',
        threadId: 'thread-a',
        offsetPx: -40,
      });
    });

    it('restores by virtualized index when mounted directly into Chronological view (documented reduced scope: nearest loaded index, not exact pixel offset)', async () => {
      savePlayPreferences({ ...DEFAULT_PLAY_PREFERENCES, readerMode: 'chronological' });
      const many = Array.from({ length: 50 }, (_, i) => {
        const id = i + 1;
        return {
          ...interaction(id, `pose ${id}`, 'thread-a'),
          // interaction()'s own timestamp template breaks down past a
          // single-digit id (`00:0${id}` produces an invalid, non-monotonic
          // string for id >= 10) — this test needs 50 correctly-chronological
          // poses, so it supplies a properly zero-padded one instead.
          timestamp: `2026-01-01T00:${String(id).padStart(2, '0')}:00Z`,
        };
      });
      saveConversationAnchor('scene:1', {
        anchor: { poseId: '50', threadId: 'thread-a', offsetPx: 0 },
        collapsed: [],
      });

      const { getByTestId } = render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          interactions={many}
          fetchNextPage={vi.fn()}
        />
      );
      const chronoContainer = getByTestId('chrono-scroll-container');

      // Without any restore, the virtualizer's default mount position is the
      // very top (scrollTop 0) -- a no-op/pre-fix implementation (or one
      // that dropped the `chronological` branch of restoreAnchor) would
      // leave it there. scrollToIndex's own scrollTo() write (polyfilled
      // above) moves it synchronously during the mount effect.
      //
      // This intentionally does NOT assert pose 50 itself becomes visible:
      // reaching an exact target index inside a virtualized list requires
      // several measure/reconcile passes when real item sizes (here, jsdom's
      // stubbed 700px `offsetHeight`) differ from `estimateSize` -- in a real
      // browser those passes are driven by ResizeObserver + rAF + native
      // scroll events, none of which jsdom actually runs, so the window
      // this test can observe converges toward, but does not reliably reach,
      // the target row. That reconciliation gap is a test-environment
      // limitation, not evidence about the production restore logic, which
      // is why Chronological view's restore is documented (see
      // restoreChronoAnchor's own comment) as reduced-scope in the first
      // place. Threads view's restore, covered exhaustively above, is exact.
      expect(chronoContainer.scrollTop).toBeGreaterThan(0);
    });
  });
});
