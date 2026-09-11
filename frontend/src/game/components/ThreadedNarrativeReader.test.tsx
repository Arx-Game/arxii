import type { ReactElement } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThreadedNarrativeReader } from './ThreadedNarrativeReader';
import { DisplaySettings } from './DisplaySettings';
import {
  DEFAULT_PLAY_PREFERENCES,
  loadConversationAnchor,
  saveConversationAnchor,
  savePlayPreferences,
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

// Anchor save/restore (#3759 Wave 6) locates poses via `getBoundingClientRect`,
// none of which jsdom computes from real layout. `poseOffsets` maps a pose id
// to the `top` its element's getBoundingClientRect should report (relative to
// a containerTop of 0, since the container itself never carries a
// `data-pose-id` and so always falls through to offset 0 below); each test
// sets it before rendering/scrolling to simulate a specific on-screen layout.
// `poseOffsetsResolver`, when set, takes precedence over the flat map — used
// by the one test that needs a pose's simulated position to depend on live
// DOM state (a real font-size CSS variable) rather than a fixed number.
let poseOffsets: Record<string, number> = {};
let poseOffsetsResolver: ((poseId: string) => number | undefined) | null = null;

/**
 * Wraps `ui` in a REAL scrollable ancestor (inline `overflow-y: auto`,
 * mirroring GameWindow.tsx's actual `feedScrollRef` div) so the anchor
 * system's `findScrollContainer` (used by every restore path) has something
 * genuine to resolve, without relying on a global geometry/style stub.
 *
 * An earlier version of this suite stubbed `scrollHeight`/`clientHeight` to
 * fixed values on `HTMLElement.prototype` globally, which made the reader's
 * OWN root element (never the real scroll container in production) resolve
 * as if it were one — masking a real production bug (#3759 review finding
 * C1) where the container-resolution effect ran once at mount and gave up
 * permanently if nothing had overflowed yet, which is always true on a cold
 * page load. This helper renders a container that's genuinely resolvable
 * (via computed `overflow-y`, matching `findScrollContainer`'s primary
 * check) so restore tests exercise the real resolution path instead.
 */
function renderInScrollAncestor(ui: ReactElement) {
  const wrap = (inner: ReactElement) => (
    <div data-testid="scroll-ancestor" style={{ overflowY: 'auto', height: '700px' }}>
      {inner}
    </div>
  );
  const utils = render(wrap(ui));
  return {
    ...utils,
    ancestor: screen.getByTestId('scroll-ancestor'),
    rerenderInner: (inner: ReactElement) => utils.rerender(wrap(inner)),
  };
}

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
    document.documentElement.style.removeProperty('--play-prose-size');
    poseOffsets = {};
    poseOffsetsResolver = null;

    // jsdom has no layout engine, so every element's offsetHeight is always
    // 0. @tanstack/react-virtual (Chronological branch) reads the scroll
    // container's offsetHeight synchronously — before any ResizeObserver
    // callback, and this repo's ResizeObserver polyfill in src/test/setup.ts
    // is a no-op besides — to decide the visible range; a 0-height container
    // makes it conclude nothing is visible and render zero rows rather than
    // all of them. Stub offsetHeight to a plausible viewport size so the
    // virtualizer computes a real, bounded window in every test.
    offsetHeightSpy = vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(700);

    // The Chronological virtualizer's own internal scroll-offset math
    // (`getMaxScrollOffset = scrollHeight - clientHeight`, used by
    // scrollToIndex/scrollToEnd) needs a real, positive overflow on ITS OWN
    // container specifically -- scoped by testid rather than stubbed
    // globally for every element. A global stub here would make
    // `findScrollContainer`'s geometry fallback resolve the reader's own
    // root as if IT were the scroll container in Threads view too, exactly
    // the production masking bug #3759 review finding C1 describes (this
    // same function backs both views' restore).
    scrollHeightSpy = vi
      .spyOn(HTMLElement.prototype, 'scrollHeight', 'get')
      .mockImplementation(function (this: HTMLElement) {
        return this.dataset.testid === 'chrono-scroll-container' ? 8000 : 0;
      });
    clientHeightSpy = vi
      .spyOn(HTMLElement.prototype, 'clientHeight', 'get')
      .mockImplementation(function (this: HTMLElement) {
        return this.dataset.testid === 'chrono-scroll-container' ? 700 : 0;
      });

    rectSpy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: HTMLElement
    ) {
      const poseId = this.dataset?.poseId;
      let top = 0;
      if (poseId !== undefined) {
        const resolved = poseOffsetsResolver?.(poseId);
        top = resolved !== undefined ? resolved : (poseOffsets[poseId] ?? 0);
      }
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
    document.documentElement.style.removeProperty('--play-prose-size');
  });

  it('keeps explicit threads collapsed and exposes keyboard accessible controls', async () => {
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        conversationRef="scene:1"
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
        conversationRef="scene:1"
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
        conversationRef="scene:1"
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
        conversationRef="scene:2"
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
        conversationRef="scene:1"
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
        conversationRef="scene:1"
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
        conversationRef="scene:1"
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
        conversationRef="scene:1"
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
        conversationRef="scene:1"
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
    // Anchored (^...$) rather than a bare substring match: #3759 Wave 9 added
    // a per-pose "Opening pose"/"Reply in <title>" role label (F4) whose
    // title is an excerpt of the root pose's OWN content -- for thread-a's
    // reply ("second"), that label literally reads "Reply in first" (the
    // root pose's content is "first"), which a bare /first|second|third/
    // substring match would also catch as a false "first".
    const texts = screen.getAllByText(/^(first|second|third)$/).map((el) => el.textContent);
    expect(texts).toEqual(['first', 'second', 'third']);
  });

  it('windows a long chronological list instead of mounting every pose', async () => {
    // #3759 Wave 9 (F1): the OLD version of this test had to click a
    // whole-list "Load earlier history" button in a loop first, because the
    // flat `historyStart` tail-slice capped Chronological's own data to the
    // last `INITIAL_PAGE_SIZE` (20) poses regardless of virtualization --
    // that whole-list windowing is gone (`chronologicalItems` now always
    // sorts the FULL `interactions` array; see its own comment), and with no
    // `hasNextPage` prop here, no "Load earlier history" button exists to
    // click at all. The bounded-mount assertion below now passes purely
    // because of `@tanstack/react-virtual` (see the offsetHeight stub in
    // beforeEach above for why that's necessary under jsdom), which is the
    // property this test actually exists to prove -- User Story 2 ("switch
    // to Chronological and read EVERYTHING in one continuous timeline")
    // without the DOM cost of mounting everything at once.
    const user = userEvent.setup();
    const many = Array.from({ length: 300 }, (_, i) =>
      interaction(i + 1, `pose ${i + 1}`, 'thread-a')
    );
    const { container } = render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        conversationRef="scene:1"
        interactions={many}
        fetchNextPage={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /chronological/i }));
    const mountedPoses = container.querySelectorAll('[data-testid="scene-messages"]');
    expect(mountedPoses.length).toBeLessThan(300);
    expect(mountedPoses.length).toBeGreaterThan(0);
  });

  it("reaches poses beyond the old flat-20 cutoff -- the virtualizer's own total size reflects the FULL interactions array, not a windowed slice (#3759 Wave 9 fix round 1 finding I-2)", async () => {
    // The test above (`mountedPoses.length < 300 && > 0`) passes identically
    // whether `chronologicalItems` holds all 300 items OR only the old
    // flat-20 tail slice -- a 20-item list ALSO mounts fewer than 300 and
    // more than 0 nodes, for the wrong reason. This asserts something that
    // actually discriminates: `chronoVirtualizer.getTotalSize()` (rendered
    // directly as the inner content div's own `height` style, right below)
    // scales with the TRUE item count. With 300 items -- even though jsdom's
    // stubbed 700px `offsetHeight` (see beforeEach) means only the handful
    // of initially-visible/overscanned rows get MEASURED at 700px, with the
    // rest staying at the 160px `estimateSize` -- the total comfortably
    // exceeds what a 20-item-capped list could ever produce (its own
    // theoretical ceiling: 20 rows all measured at 700px = 14000).
    const user = userEvent.setup();
    const many = Array.from({ length: 300 }, (_, i) =>
      interaction(i + 1, `pose ${i + 1}`, 'thread-a')
    );
    const { container } = render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        conversationRef="scene:1"
        interactions={many}
        fetchNextPage={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /chronological/i }));
    const totalSizeEl = container.querySelector<HTMLElement>(
      '[data-testid="chrono-scroll-container"] > div'
    );
    const totalSize = Number(totalSizeEl?.style.height.replace('px', ''));
    expect(totalSize).toBeGreaterThan(20000);
  });

  it('gives the Chronological scroll container a real, bounded height rather than one relying on an inert flex-1 class (#3759 review Fix round 1 CRITICAL)', async () => {
    // This file's `beforeEach` stubs `scrollHeight`/`clientHeight` directly
    // on `[data-testid="chrono-scroll-container"]` (see above) so every OTHER
    // Chronological test can exercise scroll/restore logic without a real
    // layout engine -- but that same stub means those tests CANNOT tell a
    // genuinely scrollable container from a `flex-1` class that never
    // resolves because the actual ancestor chain isn't a flex column (Wave
    // 8's regression: GameWindow.tsx's feed div and this reader's own root/
    // wrapper divs are all `display: block` from this element's own
    // perspective, so `flex-1` was inert and the container's height silently
    // collapsed to `auto`). This is deliberately the ONE Chronological test
    // that does NOT rely on that stub: `getComputedStyle` reflects an
    // explicit inline height (jsdom applies inline styles without needing a
    // layout engine) but never resolves a Tailwind utility class (no
    // stylesheet is loaded in this test environment), so it genuinely fails
    // against a class-only implementation and passes only for a real,
    // explicit bound.
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        conversationRef="scene:1"
        interactions={[interaction(1, 'first', 'thread-a')]}
        fetchNextPage={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /chronological/i }));
    const chronoContainer = screen.getByTestId('chrono-scroll-container');
    expect(window.getComputedStyle(chronoContainer).height).not.toBe('');
  });

  it('persists bulk Expand/Collapse loaded threads clicks, unlike a direct setCollapsed that bypasses saveConversationAnchor', async () => {
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        conversationRef="scene:1"
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
        conversationRef="scene:1"
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
        conversationRef="scene:1"
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
    // No `conversationRef` supplied here -- falls back to `conversationKey`,
    // which happens to already be a valid `"scene:<id>"` ref in this test.
    expect(markConversationRead).toHaveBeenCalledWith('scene:1', '2026-01-01T00:02:00Z');
  });

  it('sends conversationRef (the real server ref), not conversationKey (the localStorage key), to markConversationRead (#3759 review finding C1)', async () => {
    // The actual production bug shape: `conversationKey` can be a bare id
    // (GameWindow.tsx's localStorage anchor key), never in the server's
    // `"scene:<id>"` ref format -- conflating the two meant the server-bound
    // POST silently carried a ref no row ever matched. Uses deliberately
    // DIFFERENT values for the two props so a regression that reads the
    // wrong one is caught, not accidentally masked by them agreeing.
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="42"
        conversationRef="scene:42"
        interactions={[
          interaction(1, 'older root', 'thread-a'),
          interaction(2, 'newer root', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );

    await user.click(screen.getByRole('button', { name: /mark conversation read/i }));

    expect(markConversationRead).toHaveBeenCalledWith('scene:42', '2026-01-01T00:02:00Z');
  });

  describe('reading-position anchors (#3759 Wave 6 + review fix pass)', () => {
    it('does not save an anchor synchronously on scroll -- only after the debounce settles', async () => {
      poseOffsets = { 1: -50, 2: 100 };
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
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
      expect(loadConversationAnchor('scene:1')?.anchors.threads).toEqual({
        poseId: '1',
        threadId: 'thread-a',
        offsetPx: -50,
      });
    });

    it('attaches its scroll listener even when the scene starts empty and gets data later (#3759 review finding C1: a cold page load)', async () => {
      // Mirrors a real page load: this component mounts (per GameWindow.tsx)
      // the instant sceneId is known, while useSceneInteractions's query is
      // still in flight, so `interactions` is `[]` on the very first render
      // -- nothing has rendered/overflowed yet. A container-resolution
      // effect that resolves once at mount and permanently gives up if that
      // resolution fails (the pre-fix version of this listener) would never
      // attach for the life of this mount, no matter how much data arrived
      // afterward -- the entire save half of the feature would be dead. This
      // uses `renderInScrollAncestor` (a real ancestor, not the global
      // scrollHeight/clientHeight stub the pre-fix suite relied on) so the
      // scenario is actually representative.
      const { rerenderInner, ancestor } = renderInScrollAncestor(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[]}
          fetchNextPage={vi.fn()}
        />
      );
      expect(screen.getByText('New conversation')).toBeInTheDocument();

      poseOffsets = { 1: -25 };
      rerenderInner(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );

      fireEvent.scroll(ancestor);
      await new Promise((resolve) => setTimeout(resolve, 350));

      expect(loadConversationAnchor('scene:1')?.anchors.threads).toEqual({
        poseId: '1',
        threadId: 'thread-a',
        offsetPx: -25,
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
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );

      fireEvent.scroll(screen.getByLabelText('Story reader'));
      await new Promise((resolve) => setTimeout(resolve, 350));

      expect(loadConversationAnchor('scene:1')?.anchors.threads).toEqual({
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
          conversationRef="scene:1"
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
      expect(stored?.anchors.threads).not.toBeNull();
      // The collapse-toggle's own persisted list must survive the anchor
      // save (a stale-`storedAnchorState`-style regression would instead
      // have reverted `collapsed` to whatever it was at mount).
      expect(stored?.collapsed).toEqual([]);
    });

    it('does not persist an anchor while a non-room conversation tab is active (#3759 review finding I4, persistAnchor=false)', async () => {
      // GameWindow.tsx always uses `conversationKey={sceneFeed.sceneId}`
      // regardless of which conversation tab is active (#2165), but a
      // tab-narrowed `interactions` prop is a different, smaller pose set
      // than the room's -- so a scroll while a non-room tab is active must
      // never write into the room's shared storage row.
      poseOffsets = { 1: -20 };
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a')]}
          fetchNextPage={vi.fn()}
          persistAnchor={false}
        />
      );

      fireEvent.scroll(screen.getByLabelText('Story reader'));
      await new Promise((resolve) => setTimeout(resolve, 350));

      expect(loadConversationAnchor('scene:1')).toBeNull();
    });

    it('restores scroll position to the anchored pose once real data has arrived (mirrors the default-collapse async-arrival timing fix)', () => {
      saveConversationAnchor('scene:1', {
        anchors: {
          threads: { poseId: '2', threadId: 'thread-a', offsetPx: 40 },
          chronological: null,
        },
        collapsed: [],
      });
      const { rerenderInner, ancestor } = renderInScrollAncestor(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[]}
          fetchNextPage={vi.fn()}
        />
      );
      // No poses rendered yet — nothing to restore into, and nothing throws.
      expect(ancestor.scrollTop).toBe(0);

      poseOffsets = { 2: 300 };
      rerenderInner(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );

      // scrollTop += (pose 2's current top, 300) - (its recorded offset, 40).
      expect(ancestor.scrollTop).toBe(260);
    });

    it('falls back to the bottom when the anchored pose is not in the currently loaded set (#3759 review finding I3)', () => {
      // GameWindow.tsx no longer applies its own scroll-to-bottom fallback
      // once this scene has ANY persisted anchor (see its own bypass
      // condition), so the reader must restore that fallback itself on a
      // miss rather than silently stranding the reader at the top.
      saveConversationAnchor('scene:1', {
        anchors: {
          threads: { poseId: '999', threadId: 'thread-z', offsetPx: 40 },
          chronological: null,
        },
        collapsed: [],
      });
      poseOffsets = { 1: 0 };
      const props = (readOnly: boolean) => (
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a')]}
          fetchNextPage={vi.fn()}
          readOnly={readOnly}
        />
      );
      // Mount read-only first (restore doesn't run yet) so `ancestor` exists
      // to stub `scrollHeight` on directly -- an own-property override,
      // scoped to just this element, rather than a prototype-wide spy that
      // would affect container resolution itself (see the shared
      // scrollHeight/clientHeight mocks in beforeEach above for why that
      // matters).
      const { rerenderInner, ancestor } = renderInScrollAncestor(props(true));
      Object.defineProperty(ancestor, 'scrollHeight', { value: 5000, configurable: true });
      rerenderInner(props(false)); // triggers the restore now that the stub is in place

      // Best-effort miss: pose 999 (e.g. on an older, not-yet-fetched
      // history page) isn't found, so this falls back to the bottom instead
      // of leaving scrollTop at 0.
      expect(ancestor.scrollTop).toBe(5000);
      expect(screen.getByText('first')).toBeInTheDocument();
    });

    it('never persists an anchor while reading in read-only (historical reference) mode', async () => {
      poseOffsets = { 1: -30, 2: 60 };
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
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
        anchors: {
          threads: { poseId: '2', threadId: 'thread-a', offsetPx: 40 },
          chronological: null,
        },
        collapsed: [],
      });
      poseOffsets = { 2: 300 };
      const { ancestor } = renderInScrollAncestor(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
          readOnly
        />
      );

      expect(ancestor.scrollTop).toBe(0);
    });

    it('restores the prior live anchor when readOnly flips back to false (Return to live, Decision #5)', () => {
      saveConversationAnchor('scene:1', {
        anchors: {
          threads: { poseId: '2', threadId: 'thread-a', offsetPx: 40 },
          chronological: null,
        },
        collapsed: [],
      });
      const props = (readOnly: boolean) => (
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
          readOnly={readOnly}
        />
      );

      poseOffsets = { 2: 40 };
      const { rerenderInner, ancestor } = renderInScrollAncestor(props(false));
      // Live mount: pose 2 is already sitting exactly at its recorded offset.
      expect(ancestor.scrollTop).toBe(0);

      // Enter a historical reference on the SAME component instance (as
      // GameWindow.tsx does when the reference targets the same scene) —
      // mirrors a cached reference that never shows a loading interstitial,
      // so this is the same mounted instance the whole way through.
      rerenderInner(props(true));

      // Layout shifted while away (e.g. new poses arrived live in the
      // background) — pose 2 now sits further down.
      poseOffsets = { 2: 300 };
      rerenderInner(props(false));

      // Restored again on the readOnly:true -> false transition, even
      // though the reader's one-shot initial-mount restore already ran
      // above — proving this is the explicit return-to-live re-anchor, not
      // just the initial seed re-firing.
      expect(ancestor.scrollTop).toBe(260);
    });

    it('keeps the live anchor restored after deep-linking into reference mode and Return to live, instead of reverting to the tail slice a render later (#3759 review Fix round 1 IMPORTANT)', () => {
      // #3759 Wave 9 (F1/F2) note on this test's history: the ORIGINAL bug
      // this test guards against was a flat-array-position artifact --
      // `historyStartOverride` was a single raw INDEX into the whole
      // conversation, so a stale value left over from reference mode (a
      // different, differently-sized `interactions` array) could coincidentally
      // still be a valid-looking index into the LIVE array and get consumed
      // directly, bypassing the widen-then-retry path that would otherwise
      // re-establish it. That EXACT mechanism can no longer occur:
      // `threadWindows` (the per-thread replacement) is keyed by thread id
      // STRING, not by array position, and the live thread ('thread-a') and
      // the reference thread ('thread-ref') below use deliberately different
      // keys -- a stale entry for one key is simply never read while
      // resolving the other, collision or not. The invariant this test
      // exists to protect is still real and still worth covering, though:
      // returning to live after a reference-mode detour must not silently
      // strand a live anchor that was saved WHILE reference mode was open.
      //
      // 30 live poses (ids 1-30, one thread), mounted with NO saved anchor
      // yet -- so the initial live mount needs no widen at all and
      // `threadWindows` starts and stays empty through the live phase.
      //
      // Deep-linking into reference mode with a target pose (id 101) that's
      // outside its own thread's default tail genuinely widens the
      // reference thread's ('thread-ref') own `threadWindows` entry (a real
      // C2 widen).
      //
      // The live anchor (pose 5, outside the live thread's own default tail
      // of ids 11-30) is saved WHILE still in reference mode -- mirroring
      // "a scroll happened live in the background" (the existing "restores
      // the prior live anchor..." test above uses the same narrative). On
      // Return to live, the render-time reset (still necessary here even
      // though the ORIGINAL index-collision bug can't recur -- see its own
      // declaration-site comment for why `threadWindows` specifically still
      // needs it) clears the stale 'thread-ref' entry; Effect B's restore
      // then finds pose 5 missing from live's default tail (ids 11-30),
      // widens 'thread-a' via the normal widen-then-retry path (I2), and
      // the retry re-render finds and restores pose 5.
      const live = Array.from({ length: 30 }, (_, i) => {
        const id = i + 1;
        return {
          ...interaction(id, `live pose ${id}`, 'thread-a'),
          timestamp: `2026-01-01T00:${String(id).padStart(2, '0')}:00Z`,
        };
      });
      poseOffsets = { 5: 0 };

      const liveProps = (readOnly: boolean) => (
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={live}
          fetchNextPage={vi.fn()}
          readOnly={readOnly}
        />
      );
      const referenceInteractions = Array.from({ length: 30 }, (_, i) => {
        const id = i + 101;
        return {
          ...interaction(id, `ref pose ${id}`, 'thread-ref'),
          timestamp: `2026-02-01T00:${String(i + 1).padStart(2, '0')}:00Z`,
        };
      });
      const referenceProps = (
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={referenceInteractions}
          fetchNextPage={vi.fn()}
          readOnly
          targetPoseId="101"
        />
      );

      const { rerenderInner, ancestor } = renderInScrollAncestor(liveProps(false));
      // No anchor yet -- default tail, nothing to restore.
      expect(ancestor.querySelector('[data-pose-id="5"]')).toBeNull();

      // Deep-link into reference mode -- genuinely widens 'thread-ref''s own
      // threadWindows entry.
      rerenderInner(referenceProps);

      // A live anchor now exists (as if new poses arrived, or the user
      // scrolled, while reference mode was open).
      saveConversationAnchor('scene:1', {
        anchors: {
          threads: { poseId: '5', threadId: 'thread-a', offsetPx: 0 },
          chronological: null,
        },
        collapsed: [],
      });

      // Return to live -- the SAME component instance, per Decision #5.
      rerenderInner(liveProps(false));

      // The live anchor (pose 5) must be visible once everything settles,
      // not silently evicted a render later by a stale reset undoing
      // Effect B's just-completed restore.
      expect(ancestor.querySelector('[data-pose-id="5"]')).not.toBeNull();
    });

    it('defers the font/measure re-anchor until AFTER DisplaySettings applies the CSS variable (real GameLayout effect ordering, #3759 review finding I1)', async () => {
      // GameLayout.tsx renders `center` (GameWindow -> this reader) BEFORE
      // `sidebar` (PlaySidebar -> DisplaySettings), and React flushes
      // passive effects in that tree order -- so on a real preference
      // update, this reader's own effect fires before DisplaySettings' own
      // effect has actually applied the new CSS variable. A prior version
      // of this test drove the update through a decoupled `renderHook` and
      // mutated the fake layout BEFORE calling `update()`, which inverted
      // that ordering by construction and never actually exercised it. This
      // one renders the reader and the REAL `DisplaySettings` component as
      // siblings (reader first) and makes the simulated layout depend on
      // whatever the CSS variable's CURRENT value is, so it only reports
      // the new position once DisplaySettings' effect has actually run.
      saveConversationAnchor('scene:1', {
        anchors: {
          threads: { poseId: '2', threadId: 'thread-a', offsetPx: 40 },
          chronological: null,
        },
        collapsed: [],
      });
      document.documentElement.style.setProperty('--play-prose-size', '14px');
      poseOffsetsResolver = (poseId) => {
        if (poseId !== '2') return undefined;
        const applied = document.documentElement.style.getPropertyValue('--play-prose-size');
        return applied === '18px' ? 220 : 40;
      };

      render(
        <>
          <div data-testid="scroll-ancestor" style={{ overflowY: 'auto', height: '700px' }}>
            <ThreadedNarrativeReader
              sceneId="1"
              conversationKey="scene:1"
              conversationRef="scene:1"
              interactions={[
                interaction(1, 'first', 'thread-a'),
                interaction(2, 'second', 'thread-a'),
              ]}
              fetchNextPage={vi.fn()}
            />
          </div>
          <DisplaySettings />
        </>
      );
      const ancestor = screen.getByTestId('scroll-ancestor');
      // Initial restore: pose 2 already sitting exactly at its recorded
      // offset (the CSS var is still '14px', so the resolver returns 40).
      expect(ancestor.scrollTop).toBe(0);

      fireEvent.change(screen.getByLabelText('Prose text size'), { target: { value: '18' } });

      // If this reader's restore ran synchronously (not deferred), it would
      // run before DisplaySettings' own effect (real tree order) and see
      // the STALE '14px' value -- the resolver would still return 40, and
      // scrollTop would stay 0. Deferring via requestAnimationFrame lets
      // DisplaySettings' effect apply the new CSS variable first, so the
      // resolver now returns 220 and this computes the correct delta.
      await waitFor(() => {
        expect(ancestor.scrollTop).toBe(180);
      });
    });

    it('does not re-restore (and so never falls back to the bottom) on a preference change while a non-room tab is active (#3759 review finding, second pass: Effect C also gated on persistAnchor)', async () => {
      const scrollHeightSpy = vi
        .spyOn(HTMLElement.prototype, 'scrollHeight', 'get')
        .mockImplementation(function (this: HTMLElement) {
          // Deliberately nonzero so a wrongly-triggered I3 fallback would be
          // an OBSERVABLE change here, not coincidentally still 0.
          return this.dataset.testid === 'scroll-ancestor' ? 9000 : 0;
        });
      try {
        // Start with a matching anchor (pose 1, present, offset 0) so the
        // one-shot initial-mount restore (Effect A -- unaffected by this
        // fix, out of scope for this pass) is a clean, harmless hit. This
        // isolates the test to Effect C's own guard.
        saveConversationAnchor('scene:1', {
          anchors: {
            threads: { poseId: '1', threadId: 'thread-a', offsetPx: 0 },
            chronological: null,
          },
          collapsed: [],
        });
        const props = (persistAnchor: boolean) => (
          <>
            <div data-testid="scroll-ancestor" style={{ overflowY: 'auto', height: '700px' }}>
              <ThreadedNarrativeReader
                sceneId="1"
                conversationKey="scene:1"
                conversationRef="scene:1"
                interactions={[interaction(1, 'first', 'thread-a')]}
                fetchNextPage={vi.fn()}
                persistAnchor={persistAnchor}
              />
            </div>
            <DisplaySettings />
          </>
        );
        const { rerender } = render(props(true));
        const ancestor = screen.getByTestId('scroll-ancestor');
        expect(ancestor.scrollTop).toBe(0);

        // Now simulate the real corruption vector this guard prevents: the
        // user has switched to a non-room tab (persistAnchor -> false), and
        // the room's own persisted anchor (poseId '999') no longer matches
        // anything in this narrower, tab-scoped interaction set. Without
        // gating Effect C on persistAnchor too (previously gated only on
        // `readOnly`), a preference change would call restoreThreadsAnchor,
        // fail to find pose 999, and fall into the I3 miss-fallback
        // (scrollTop = scrollHeight) -- jumping this tab's feed to the
        // bottom on every preference change, a behavior that didn't exist
        // before the I3 fallback was added (pre-fix, a miss was a silent
        // no-op).
        saveConversationAnchor('scene:1', {
          anchors: {
            threads: { poseId: '999', threadId: 'thread-z', offsetPx: 0 },
            chronological: null,
          },
          collapsed: [],
        });
        rerender(props(false));
        expect(ancestor.scrollTop).toBe(0); // the rerender alone restores nothing

        fireEvent.change(screen.getByLabelText('Prose text size'), { target: { value: '18' } });

        // Give a (would-be, pre-fix) rAF-scheduled restore every chance to
        // run before asserting nothing changed.
        await new Promise((resolve) => requestAnimationFrame(resolve));
        await new Promise((resolve) => requestAnimationFrame(resolve));

        expect(ancestor.scrollTop).toBe(0);
      } finally {
        scrollHeightSpy.mockRestore();
      }
    });

    it('debounces anchor saves in Chronological view too, using its own virtualized scroll container', async () => {
      poseOffsets = { 1: -40, 2: 90 };
      const user = userEvent.setup();
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );
      await user.click(screen.getByRole('button', { name: /chronological/i }));

      fireEvent.scroll(screen.getByTestId('chrono-scroll-container'));
      expect(loadConversationAnchor('scene:1')).toBeNull();

      await new Promise((resolve) => setTimeout(resolve, 350));
      // Chronological mode writes into its OWN anchor slot (#3759 review
      // finding I5) -- switching modes must never write over Threads'.
      expect(loadConversationAnchor('scene:1')?.anchors.chronological).toEqual({
        poseId: '1',
        threadId: 'thread-a',
        offsetPx: -40,
      });
      expect(loadConversationAnchor('scene:1')?.anchors.threads).toBeNull();
    });

    it('keeps a saved Threads anchor unchanged after saving a DIFFERENT Chronological anchor and switching back (#3759 review Fix round 1: strengthened I5 round trip)', async () => {
      // The weaker version of this test only asserted the OTHER slot was
      // null after one save -- an implementation that blindly zeroed the
      // other mode's slot on every write (rather than genuinely keeping two
      // independent slots) would also pass that. This does the actual round
      // trip the ratified Decision #2 requires: save a real Threads anchor,
      // switch to Chronological, save a DIFFERENT anchor there, switch back
      // to Threads, and assert the FIRST anchor survived byte-for-byte.
      poseOffsets = { 1: -40, 2: 90 };
      const user = userEvent.setup();
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );

      // Save a Threads anchor (pose 1, offset -40).
      fireEvent.scroll(screen.getByLabelText('Story reader'));
      await new Promise((resolve) => setTimeout(resolve, 350));
      const threadsAnchor = loadConversationAnchor('scene:1')?.anchors.threads;
      expect(threadsAnchor).toEqual({ poseId: '1', threadId: 'thread-a', offsetPx: -40 });

      // Switch to Chronological and save a DIFFERENT anchor (pose 2, offset -5
      // -- closer to the container's top than pose 1's -100, so it's the one
      // `findTopVisiblePoseId` picks as "topmost").
      poseOffsets = { 1: -100, 2: -5 };
      await user.click(screen.getByRole('button', { name: /chronological/i }));
      fireEvent.scroll(screen.getByTestId('chrono-scroll-container'));
      await new Promise((resolve) => setTimeout(resolve, 350));
      expect(loadConversationAnchor('scene:1')?.anchors.chronological).toEqual({
        poseId: '2',
        threadId: 'thread-a',
        offsetPx: -5,
      });

      // Switch back to Threads -- the FIRST anchor must be exactly what it
      // was, untouched by the Chronological save in between.
      await user.click(screen.getByRole('button', { name: /^threads$/i }));
      expect(loadConversationAnchor('scene:1')?.anchors.threads).toEqual(threadsAnchor);
    });

    it('does not persist a Chronological-view anchor while a non-room conversation tab is active (#3759 review finding I4)', async () => {
      poseOffsets = { 1: -40 };
      const user = userEvent.setup();
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a')]}
          fetchNextPage={vi.fn()}
          persistAnchor={false}
        />
      );
      await user.click(screen.getByRole('button', { name: /chronological/i }));

      fireEvent.scroll(screen.getByTestId('chrono-scroll-container'));
      await new Promise((resolve) => setTimeout(resolve, 350));

      expect(loadConversationAnchor('scene:1')).toBeNull();
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
        anchors: {
          threads: null,
          chronological: { poseId: '50', threadId: 'thread-a', offsetPx: 0 },
        },
        collapsed: [],
      });

      const { getByTestId } = render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
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

    it('falls back to the end of the loaded Chronological page when the anchored pose is not found (#3759 review finding I3)', () => {
      savePlayPreferences({ ...DEFAULT_PLAY_PREFERENCES, readerMode: 'chronological' });
      saveConversationAnchor('scene:1', {
        anchors: {
          threads: null,
          chronological: { poseId: '999', threadId: 'thread-z', offsetPx: 0 },
        },
        collapsed: [],
      });

      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a'), interaction(2, 'second', 'thread-a')]}
          fetchNextPage={vi.fn()}
        />
      );
      const chronoContainer = screen.getByTestId('chrono-scroll-container');

      // scrollToEnd's own scrollTo() write (polyfilled above) moves scrollTop
      // away from 0 -- a no-op/pre-fix implementation (idx === -1 silently
      // returning) would leave it there.
      expect(chronoContainer.scrollTop).toBeGreaterThan(0);
    });

    it('widens the window to include an anchored pose outside the default tail, instead of jumping to the bottom (#3759 review finding I2)', () => {
      const many = Array.from({ length: 51 }, (_, i) => {
        const id = i + 1;
        return {
          ...interaction(id, `pose ${id}`, 'thread-a'),
          timestamp: `2026-01-01T00:${String(id).padStart(2, '0')}:00Z`,
        };
      });
      saveConversationAnchor('scene:1', {
        anchors: {
          threads: { poseId: '10', threadId: 'thread-a', offsetPx: 0 },
          chronological: null,
        },
        collapsed: [],
      });
      poseOffsets = { 10: 0 };

      const { ancestor } = renderInScrollAncestor(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={many}
          fetchNextPage={vi.fn()}
        />
      );

      // #3759 Wave 9: pose 10 sits at index 9 of this thread's own 51-pose
      // list -- well outside its default per-thread tail window (51 - 20 =
      // start index 31), which the untouched default alone would never
      // include. A bottom-jump implementation would never render it at all;
      // the actual fix widens 'thread-a' to show the whole thread (#3759
      // Wave 9 F1/F2's own simplification -- see `widenThreadWindow`'s
      // comment) rather than jumping away.
      expect(document.querySelector('[data-pose-id="10"]')).not.toBeNull();
      // The real fallback never fired -- scrollTop reflects the anchor's own
      // computed position, not a jump to scrollHeight.
      expect(ancestor.scrollTop).toBe(0);
      // And the stored anchor itself is untouched by this restore.
      expect(loadConversationAnchor('scene:1')?.anchors.threads).toEqual({
        poseId: '10',
        threadId: 'thread-a',
        offsetPx: 0,
      });
    });

    it('suppresses the anchor save the bottom-fallback scroll itself would otherwise trigger, so a genuine miss never overwrites the real anchor (#3759 review finding I2)', async () => {
      // Pose 999 is genuinely absent from `interactions` (not merely outside
      // the tail window) -- the widen path can't help, so this exercises the
      // bottom-fallback itself.
      saveConversationAnchor('scene:1', {
        anchors: {
          threads: { poseId: '999', threadId: 'thread-z', offsetPx: 40 },
          chronological: null,
        },
        collapsed: [],
      });
      poseOffsets = { 1: 0 };
      const props = (readOnly: boolean) => (
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a')]}
          fetchNextPage={vi.fn()}
          readOnly={readOnly}
        />
      );
      // Mount read-only first (restore doesn't run yet) so `ancestor` exists
      // to stub `scrollHeight` on directly, mirroring the I3 fallback test
      // above.
      const { rerenderInner, ancestor } = renderInScrollAncestor(props(true));
      Object.defineProperty(ancestor, 'scrollHeight', { value: 5000, configurable: true });
      rerenderInner(props(false)); // triggers the restore + bottom-fallback now that the stub is in place

      expect(ancestor.scrollTop).toBe(5000);

      // A real browser fires a native 'scroll' event as a side effect of
      // that fallback's own `scrollTop` write -- simulate it (jsdom doesn't
      // fire one automatically for a plain property assignment) and let the
      // debounced save listener see it.
      fireEvent.scroll(ancestor);
      await new Promise((resolve) => setTimeout(resolve, 350));

      // The suppression flag absorbs exactly that one scroll -- the original
      // anchor (pose 999) survives unchanged, never overwritten with
      // whatever pose the fallback scroll landed on.
      expect(loadConversationAnchor('scene:1')?.anchors.threads).toEqual({
        poseId: '999',
        threadId: 'thread-z',
        offsetPx: 40,
      });
    });
  });

  describe('collapse persistence guard (#3759 review finding I1)', () => {
    it('does not persist a thread-collapse toggle while a non-room conversation tab is active (persistAnchor=false)', async () => {
      const user = userEvent.setup();
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[
            interaction(1, 'older root', 'thread-a'),
            interaction(2, 'newer root', 'thread-b'),
          ]}
          fetchNextPage={vi.fn()}
          persistAnchor={false}
        />
      );
      // thread-b (more recent) starts expanded -- collapse it. The toggle
      // still WORKS (in-memory `collapsed` state changes, per Decision #5 --
      // a reference/narrowed reader may still collapse threads for its own
      // reading session), it just must not write into shared storage.
      await user.click(screen.getByRole('button', { name: /writer 2.*1 pose/i }));
      expect(screen.queryByText('newer root')).not.toBeInTheDocument();
      expect(loadConversationAnchor('scene:1')).toBeNull();
    });

    it('does not persist a thread-collapse toggle while reading a historical reference (readOnly)', async () => {
      const user = userEvent.setup();
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[
            interaction(1, 'older root', 'thread-a'),
            interaction(2, 'newer root', 'thread-b'),
          ]}
          fetchNextPage={vi.fn()}
          readOnly
        />
      );
      await user.click(screen.getByRole('button', { name: /writer 2.*1 pose/i }));
      expect(screen.queryByText('newer root')).not.toBeInTheDocument();
      expect(loadConversationAnchor('scene:1')).toBeNull();
    });
  });

  describe('deep-link target seek (#3759 review finding C2)', () => {
    it('seeds the window to include a target pose outside the default tail window, scrolls to it, and highlights it', () => {
      const many = Array.from({ length: 51 }, (_, i) => {
        const id = i + 1;
        return {
          ...interaction(id, `pose ${id}`, 'thread-a'),
          timestamp: `2026-01-01T00:${String(id).padStart(2, '0')}:00Z`,
        };
      });
      const scrollIntoViewSpy = vi
        .spyOn(Element.prototype, 'scrollIntoView')
        .mockImplementation(() => {});

      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={many}
          fetchNextPage={vi.fn()}
          readOnly
          targetPoseId="10"
        />
      );

      // #3759 Wave 9: pose 10 sits at index 9 of this (sole) thread's own
      // 51-pose list -- well outside its default per-thread tail window
      // (51 - 20 = start index 31, i.e. only the last-20-through-50th poses
      // render by default), which is not reachable without a "Load earlier
      // replies" click under the default per-thread window alone. The C2
      // seek widens 'thread-a' to show the whole thread instead.
      const targetEl = document.querySelector('[data-pose-id="10"]');
      expect(targetEl).not.toBeNull();
      expect(scrollIntoViewSpy).toHaveBeenCalledWith(expect.objectContaining({ block: 'center' }));
      expect(targetEl).toHaveAttribute('data-highlighted', 'true');

      scrollIntoViewSpy.mockRestore();
    });

    it('clears the highlight again after the brief highlight window elapses', async () => {
      vi.useFakeTimers();
      try {
        const many = Array.from({ length: 51 }, (_, i) => {
          const id = i + 1;
          return {
            ...interaction(id, `pose ${id}`, 'thread-a'),
            timestamp: `2026-01-01T00:${String(id).padStart(2, '0')}:00Z`,
          };
        });
        vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {});

        render(
          <ThreadedNarrativeReader
            sceneId="1"
            conversationKey="scene:1"
            conversationRef="scene:1"
            interactions={many}
            fetchNextPage={vi.fn()}
            readOnly
            targetPoseId="10"
          />
        );

        expect(document.querySelector('[data-pose-id="10"]')).toHaveAttribute(
          'data-highlighted',
          'true'
        );

        await vi.advanceTimersByTimeAsync(2100);

        expect(document.querySelector('[data-pose-id="10"]')).not.toHaveAttribute(
          'data-highlighted'
        );
      } finally {
        vi.useRealTimers();
      }
    });

    it("uncollapses the target pose's own thread when it is NOT the most-recently-active one (#3759 review Fix round 1 IMPORTANT)", () => {
      // Two threads: 'thread-old' (poses 1-3) and 'thread-new' (poses 4-5,
      // more recent) -- the default-collapse rule expands only 'thread-new',
      // collapsing 'thread-old'. The deep-link target (pose 2) lives in the
      // COLLAPSED thread -- the ORDINARY multi-thread case a single-thread
      // 51-pose fixture (the test above) structurally cannot exercise, since
      // a single group is never collapsed at all.
      const interactionsList = [
        interaction(1, 'old root', 'thread-old'),
        interaction(2, 'old reply target', 'thread-old'),
        interaction(3, 'old reply', 'thread-old'),
        interaction(4, 'new root', 'thread-new'),
        interaction(5, 'new reply', 'thread-new'),
      ];
      const scrollIntoViewSpy = vi
        .spyOn(Element.prototype, 'scrollIntoView')
        .mockImplementation(() => {});

      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={interactionsList}
          fetchNextPage={vi.fn()}
          readOnly
          targetPoseId="2"
        />
      );

      const targetEl = document.querySelector('[data-pose-id="2"]');
      expect(targetEl).not.toBeNull();
      expect(targetEl).toHaveAttribute('data-highlighted', 'true');
      expect(scrollIntoViewSpy).toHaveBeenCalledWith(expect.objectContaining({ block: 'center' }));
      // thread-old's own toggle now reports expanded, not just the target
      // pose happening to be present.
      expect(screen.getByRole('button', { name: /writer 1.*3 poses/i })).toHaveAttribute(
        'aria-expanded',
        'true'
      );

      scrollIntoViewSpy.mockRestore();
    });
  });

  describe('per-thread windowing and demo-fidelity gaps (#3759 Wave 9)', () => {
    /** N poses in one thread, with real, monotonically increasing timestamps
     * (unlike the bare `interaction()` helper, whose own timestamp template
     * only produces a valid string for single-digit ids). */
    const manyInThread = (count: number, threadId = 'thread-a', startId = 1): Interaction[] =>
      Array.from({ length: count }, (_, i) => {
        const id = startId + i;
        return {
          ...interaction(id, `pose ${id}`, threadId),
          timestamp: `2026-01-0${1 + Math.floor(i / 1000)}T${String(Math.floor(i / 60) % 24).padStart(2, '0')}:${String(i % 60).padStart(2, '0')}:00Z`,
        };
      });

    it('renders every thread header on mount, oldest roots first, without any "Load earlier history" click (#3759 review finding F1, the demo-fidelity reviewer\'s own proposed mechanical companion)', () => {
      // 25 single-pose threads (> THREAD_PAGE_SIZE) spread across a wide
      // timeline -- under the OLD flat `historyStart` tail-slice (taken
      // BEFORE grouping by thread_id), only the last 20 by ARRAY POSITION
      // would have rendered at all; the other 5 threads' headers would have
      // been entirely absent, not even collapsed. `groups` now derives from
      // the full `interactions` array, so every thread gets a header row
      // regardless of where its pose falls.
      const threads = Array.from({ length: 25 }, (_, i) => ({
        ...interaction(i + 1, `root ${i + 1}`, `thread-${i}`),
        timestamp: `2026-01-01T${String(i).padStart(2, '0')}:00:00Z`,
      }));
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={threads}
          fetchNextPage={vi.fn()}
        />
      );
      expect(
        screen.queryByRole('button', { name: /load earlier history/i })
      ).not.toBeInTheDocument();
      expect(document.querySelectorAll('[data-thread-id]')).toHaveLength(25);
    });

    it('windows an expanded thread to THREAD_PAGE_SIZE poses by default, with a per-thread "Load earlier replies" control that reveals more on click', async () => {
      // The issue's own Acceptance workload: a single, very long thread must
      // only render THREAD_PAGE_SIZE (20) DOM nodes by default when
      // expanded, not all of them -- the sole thread here is also
      // necessarily the "most recently active" one, so it starts expanded
      // by the existing default-collapse rule.
      const user = userEvent.setup();
      const { container } = render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={manyInThread(45)}
          fetchNextPage={vi.fn()}
        />
      );
      expect(container.querySelectorAll('[data-testid="scene-messages"]')).toHaveLength(20);
      const loadEarlier = screen.getByRole('button', {
        name: /load earlier replies · 25 before this page/i,
      });

      await user.click(loadEarlier);

      expect(container.querySelectorAll('[data-testid="scene-messages"]')).toHaveLength(40);
      expect(
        screen.getByRole('button', { name: /load earlier replies · 5 before this page/i })
      ).toBeInTheDocument();
    });

    it('surfaces a "Load later replies" control, and lets it catch a thread back up, once new poses arrive after the user has paged into that thread\'s history', async () => {
      // #3759 Wave 9 open decision (see the wave brief section 1 and this
      // PR's report for the full reasoning): `threadWindows` freezes an
      // ABSOLUTE `end` index once a thread's window is first touched (by a
      // "Load earlier replies" click here), unlike the untouched DEFAULT
      // (which always recomputes from the thread's CURRENT length and so
      // never falls behind). If poses then arrive in that thread while the
      // frozen `end` is still the old, smaller length, the window
      // genuinely no longer reaches either true end -- "Load earlier
      // replies" AND "Load later replies" both need to be live at once,
      // which this test also exercises.
      const user = userEvent.setup();
      const { container, rerender } = render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={manyInThread(45)}
          fetchNextPage={vi.fn()}
        />
      );
      await user.click(
        screen.getByRole('button', { name: /load earlier replies · 25 before this page/i })
      );
      expect(container.querySelectorAll('[data-testid="scene-messages"]')).toHaveLength(40);
      expect(screen.queryByRole('button', { name: /load later replies/i })).not.toBeInTheDocument();

      // 5 more poses arrive live in the same thread -- the frozen window
      // (indices 5..45 of what's now a 50-pose thread) no longer reaches
      // either the true start (0) or the true end (50).
      rerender(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={manyInThread(50)}
          fetchNextPage={vi.fn()}
        />
      );
      expect(
        screen.getByRole('button', { name: /load earlier replies · 5 before this page/i })
      ).toBeInTheDocument();
      const loadLater = screen.getByRole('button', { name: /load later replies/i });

      await user.click(loadLater);

      // Window is now [5, 50) of the 50-pose thread -- 45 poses shown, the
      // 5 new arrivals now included, and "Load later" has nothing left to
      // reveal.
      expect(container.querySelectorAll('[data-testid="scene-messages"]')).toHaveLength(45);
      expect(screen.queryByRole('button', { name: /load later replies/i })).not.toBeInTheDocument();
    });

    it("shows the root pose's excerpt and timestamp on the thread header (#3759 review finding F3)", () => {
      const longContent =
        'There is a difference between knowing a thing and being able to prove it, and the difference matters more than either of us would like to admit tonight.';
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[
            { ...interaction(1, longContent, 'thread-a'), timestamp: '2026-01-01T00:01:00Z' },
          ]}
          fetchNextPage={vi.fn()}
        />
      );
      // 84-char excerpt (the default `excerptOf` length) followed by an
      // ellipsis, since `longContent` is well over 84 characters.
      const excerpt = `${longContent.slice(0, 84)}…`;
      expect(screen.getByText((text) => text.startsWith(excerpt))).toBeInTheDocument();
      // Same locale-formatted timestamp convention PoseUnit.tsx uses for
      // every per-pose timestamp elsewhere in the reader.
      expect(
        screen.getByText(new Date('2026-01-01T00:01:00Z').toLocaleString(), { exact: false })
      ).toBeInTheDocument();
    });

    it('labels each pose "Opening pose" or "Reply in <title>" (#3759 review finding F4)', () => {
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[
            interaction(1, 'root content', 'thread-a'),
            interaction(2, 'reply', 'thread-a'),
          ]}
          fetchNextPage={vi.fn()}
        />
      );
      expect(screen.getByText('Opening pose')).toBeInTheDocument();
      expect(screen.getByText('Reply in root content')).toBeInTheDocument();
    });

    it('strips MU*-style color codes and markdown from the header excerpt and role label instead of leaking raw markup (#3759 Wave 9 fix round 1 finding I-1)', () => {
      // `|w`...`|n` is a MU* color code (see `formatParser.ts`); `**bold**`
      // is markdown -- every OTHER render path (PoseUnit.tsx via
      // `<FormattedContent>`) parses this before display. `excerptOf` is
      // plain text, not JSX, so it strips the markup itself rather than
      // rendering it.
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[
            interaction(1, '|wSomething|n happened at the **broken seal**', 'thread-a'),
            interaction(2, 'a reply', 'thread-a'),
          ]}
          fetchNextPage={vi.fn()}
        />
      );
      // Both the thread header's own excerpt AND the reply's "Reply in
      // <title>" label derive from the same root content, so the stripped
      // phrase appears twice: once in the header (excerpt + timestamp),
      // once in the role label.
      expect(
        screen.getAllByText('Something happened at the broken seal', { exact: false })
      ).toHaveLength(2);
      expect(
        screen.getByText('Reply in Something happened at the broken seal')
      ).toBeInTheDocument();
      // The mocked `SceneMessages` below (this file's own mock, standing in
      // for the REAL component -- which parses markup via
      // `<FormattedContent>`, untested here) legitimately still renders the
      // raw pose content verbatim -- only the header excerpt and role label
      // (this component's OWN plain-text rendering) need to be markup-free,
      // which the exact stripped-phrase matches above already prove.
    });

    it('jumps to and expands the most-recently-active thread when "Latest activity" is clicked (#3759 review finding F5)', async () => {
      const user = userEvent.setup();
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[
            interaction(1, 'older root', 'thread-a'),
            interaction(2, 'newer root', 'thread-b'),
          ]}
          fetchNextPage={vi.fn()}
        />
      );
      // thread-b (more recent) starts expanded -- collapse everything first
      // so "Latest activity" has real work to do.
      await user.click(screen.getByRole('button', { name: /collapse loaded threads/i }));
      expect(screen.queryByText('newer root')).not.toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: /latest activity/i }));

      expect(screen.getByText('newer root')).toBeInTheDocument();
    });

    it('never renders "Mark conversation read" while reading a historical reference (#3759 review finding F6)', () => {
      render(
        <ThreadedNarrativeReader
          sceneId="1"
          conversationKey="scene:1"
          conversationRef="scene:1"
          interactions={[interaction(1, 'first', 'thread-a')]}
          fetchNextPage={vi.fn()}
          readOnly
        />
      );
      expect(
        screen.queryByRole('button', { name: /mark conversation read/i })
      ).not.toBeInTheDocument();
    });
  });
});
