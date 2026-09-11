import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronDown, ChevronRight, MessageCircle, Reply } from 'lucide-react';
import { SceneMessages } from '@/scenes/components/SceneMessages';
import type { Interaction } from '@/scenes/types';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { ReadingAnchor } from '../playPreferences';
import {
  loadConversationAnchor,
  saveConversationAnchor,
  usePlayPreferences,
} from '../playPreferences';
import { usePoseReadTracking } from '../hooks/usePoseReadTracking';
import { markConversationRead } from '../playQueries';

const INITIAL_PAGE_SIZE = 20;

/**
 * Wraps one rendered pose in the element `usePoseReadTracking` dwell-tracks.
 *
 * In Chronological view the row wrapper already carries
 * `ref={chronoVirtualizer.measureElement}` (Task 10) — a second, different
 * `ref` on the same element would silently drop one of the two assignments.
 * Rather than merge refs, this wraps just the pose's own content in its own
 * inner element nested inside that row, so the virtualizer keeps measuring
 * the row and this component independently dwell-tracks the pose within it.
 * In Threads view there's no existing ref to collide with, but the same
 * wrapper is reused there for one code path instead of two.
 */
function PoseReadTarget({
  pose,
  observe,
  highlighted,
  children,
}: {
  pose: { id: number; timestamp: string };
  observe: (element: HTMLElement, pose: { id: number; timestamp: string }) => () => void;
  /** True for ~2s right after this pose was scrolled to as a deep-link target (#3759 C2). */
  highlighted?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    return observe(element, pose);
    // Depend on pose.id/pose.timestamp (stable primitives), not the pose
    // object itself: the caller passes a fresh `{ id, timestamp }` literal
    // on every render, so an object-identity dep would re-run this effect
    // (and thus unobserve/re-observe the element) every render instead of
    // only when the pose actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [observe, pose.id, pose.timestamp]);
  // `data-pose-id` is the stable DOM handle the anchor system (#3759 Wave 6)
  // uses to find "the pose the user was reading" again after a resize, font
  // change, or history-page insertion -- see findScrollContainer/
  // findTopVisiblePoseId below. `data-highlighted` is the same kind of handle
  // for the deep-link target highlight (#3759 review finding C2): a
  // CSS-only, transition-based ring rather than an animation, so it degrades
  // to an instant, non-distracting state change under `prefers-reduced-motion`
  // (see the `motion-reduce:transition-none` utility below).
  return (
    <div
      ref={ref}
      data-pose-id={pose.id}
      data-highlighted={highlighted ? 'true' : undefined}
      className={
        highlighted
          ? 'rounded ring-2 ring-primary transition-shadow duration-300 motion-reduce:transition-none'
          : undefined
      }
    >
      {children}
    </div>
  );
}

/**
 * Walks up from `start` to find the nearest scrollable ancestor. In Threads
 * view the reader has no scroll container of its own -- GameWindow.tsx's
 * `feedScrollRef` div is the real one -- so anchor restore locates it this
 * way rather than threading a ref down through GameWindow, which would
 * couple the two components more tightly than the feature needs.
 *
 * Checks the computed `overflow-y` FIRST, not just current geometry
 * (`scrollHeight > clientHeight`): GameWindow.tsx's real container is
 * `overflow-y-auto` unconditionally (a real Tailwind class, reflected in
 * `getComputedStyle` in production), so this resolves it correctly even
 * when nothing currently overflows -- e.g. a scene that's still loading (no
 * poses yet) or short enough to fit on screen. Relying on geometry alone
 * (the original version of this function) meant a cold page load, where the
 * reader mounts before its interactions query resolves, could never resolve
 * a container at all on that first pass -- see the effect below for why
 * that mattered for more than just restore.
 */
function findScrollContainer(start: HTMLElement | null): HTMLElement | null {
  let node: HTMLElement | null = start;
  while (node) {
    const overflowY = window.getComputedStyle(node).overflowY;
    if (overflowY === 'auto' || overflowY === 'scroll' || node.scrollHeight > node.clientHeight) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

/**
 * Finds the pose currently occupying the top of `container`'s visible area:
 * the last pose whose top edge has scrolled at or above the container's own
 * top (i.e. it's the one "in charge" of the top of the viewport), or the
 * very first pose if none have scrolled past yet. Returns the pose's id and
 * its offset (px, negative when partially scrolled past) relative to the
 * container's top -- the same coordinate space `offsetPx` is stored and
 * restored in.
 */
function findTopVisiblePoseId(container: HTMLElement): { poseId: string; offsetPx: number } | null {
  const poseEls = Array.from(container.querySelectorAll<HTMLElement>('[data-pose-id]'));
  if (poseEls.length === 0) return null;
  const containerTop = container.getBoundingClientRect().top;
  let best: HTMLElement | null = null;
  let bestOffset = -Infinity;
  for (const el of poseEls) {
    const offset = el.getBoundingClientRect().top - containerTop;
    if (offset <= 0 && offset > bestOffset) {
      bestOffset = offset;
      best = el;
    }
  }
  if (!best) {
    best = poseEls[0];
    bestOffset = best.getBoundingClientRect().top - containerTop;
  }
  const poseId = best.dataset.poseId;
  return poseId ? { poseId, offsetPx: bestOffset } : null;
}

interface ThreadedNarrativeReaderProps {
  sceneId: string;
  conversationKey: string;
  /**
   * The REAL server-format conversation ref (#3759 review finding C1) --
   * what `_conversation()` on the backend actually emits for this
   * conversation (e.g. `"scene:42"`, or a reference-mode's `reference.key`,
   * which is already in that exact shape). Distinct from `conversationKey`,
   * which stays the localStorage anchor/collapse key and can be a bare id
   * (`GameWindow.tsx` passes `sceneFeed.sceneId` there, unchanged) --
   * `conversationKey` and the server's conversation ref are NOT
   * interchangeable, and conflating them is exactly how "Mark conversation
   * read" silently no-op'd in production (sent a bare scene id where the
   * server expects `"scene:<id>"`, so no row's ref ever matched).
   *
   * REQUIRED, deliberately with no `?? conversationKey`-style fallback
   * (#3759 review Fix round 1): a fallback would silently re-arm the exact
   * C1 bug for any future caller that forgets to pass this prop -- the
   * backend's 400 rejection of an unrecognized ref is defense in depth, not
   * a substitute for this compile-time guarantee. Every caller, including
   * standalone/test renders, must supply the real value explicitly.
   */
  conversationRef: string;
  interactions: Interaction[];
  hasNextPage?: boolean;
  fetchNextPage: () => void;
  onAvatarClick?: (persona: PoseUnitAvatarClickPersona) => void;
  onAddTarget?: (name: string) => void;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
  onReply?: (interaction: Interaction) => void;
  readOnly?: boolean;
  /**
   * Whether this render represents the scene's primary/room view, as opposed
   * to a tab-narrowed conversation (whisper/place/target). GameWindow.tsx
   * always renders this component with `conversationKey={sceneFeed.sceneId}`
   * regardless of which conversation tab is active (#2165), but a
   * tab-narrowed `interactions` prop is a *different, smaller* pose set than
   * the room's — saving an anchor computed from it into the room's shared
   * storage row would silently overwrite/corrupt the room's own anchor with
   * a pose id that isn't even in the room feed (#3759 review finding I4).
   * Defaults to `true` so standalone/test callers are unaffected; GameWindow
   * passes `activeConvKey === 'room'`.
   */
  persistAnchor?: boolean;
  /**
   * The pose id a deep link (a search result or a "Recent conversations" row
   * in `HistoryNavigator`) opened this reader to (#3759 review finding C2).
   * `GamePage.tsx`'s reference-mode `interactions` prop is a fixed +-25-pose
   * window around this pose, but the reader's own tail-slice
   * (`historyStart`) otherwise always shows the LAST `INITIAL_PAGE_SIZE`
   * poses of whatever window it's handed -- for a target sitting anywhere
   * but the last 20 of that window, the tail-slice alone renders everything
   * BUT the pose the user actually opened. When set and present in
   * `interactions`, the reader widens `historyStartOverride` to include it
   * (with a little context above), then scrolls to and briefly highlights
   * its `[data-pose-id]` element once mounted. Absent in live mode, where
   * the existing tail-slice default is unaffected.
   */
  targetPoseId?: string;
}

interface Group {
  key: string;
  interactions: Interaction[];
}

/** A wide, accessible reader for long-form scene poses. */
export function ThreadedNarrativeReader({
  sceneId,
  conversationKey,
  conversationRef,
  interactions,
  hasNextPage,
  fetchNextPage,
  onAvatarClick,
  onAddTarget,
  onAttachAction,
  onReply,
  readOnly = false,
  persistAnchor = true,
  targetPoseId,
}: ThreadedNarrativeReaderProps) {
  const [historyStartOverride, setHistoryStartOverride] = useState<number | null>(null);
  // #3759 review finding, minor fold-in: `historyStartOverride` is
  // component-local, live-feed tail-slice state. Entering/leaving reference
  // mode reuses this SAME component instance when the scene matches
  // (Decision #5), but a reference's `interactions` prop is a completely
  // different (smaller, fixed +-25-pose window) array than the live feed's --
  // a stale override index computed against one array is meaningless (or
  // out-of-bounds) against the other. Reset on every ACTUAL readOnly
  // transition (never on mount, where there is nothing stale to clear) --
  // guarded by a ref rather than a bare `[readOnly]` dependency so it never
  // fires on the initial render. Declared as the FIRST effect in this
  // component (before restoreThreadsAnchor/Effect A/B/the deep-link seek
  // effect below, all of which can also write `historyStartOverride`) so
  // that whichever of THOSE effects fires in the SAME commit -- entering
  // reference mode WITH a target pose, or leaving it back into a live anchor
  // miss -- runs its own `setHistoryStartOverride` call AFTER this one in
  // the same effect flush and therefore wins (same-batch, last-call-wins).
  const prevReadOnlyForResetRef = useRef(readOnly);
  useEffect(() => {
    if (prevReadOnlyForResetRef.current === readOnly) return;
    prevReadOnlyForResetRef.current = readOnly;
    setHistoryStartOverride(null);
  }, [readOnly]);
  const historyStart = historyStartOverride ?? Math.max(0, interactions.length - INITIAL_PAGE_SIZE);
  const visibleInteractions = interactions.slice(historyStart);
  const groups = useMemo(() => {
    const grouped = new Map<string, Interaction[]>();
    for (const interaction of visibleInteractions) {
      // Legacy interactions have no reply topology and therefore each remain
      // an independent root. Only explicit server thread ids group replies.
      const key = interaction.thread_id || `legacy:${interaction.id}`;
      const rows = grouped.get(key) ?? [];
      rows.push(interaction);
      grouped.set(key, rows);
    }
    return [...grouped.entries()]
      .map(
        ([key, rows]): Group => ({
          key,
          interactions: [...rows].sort(
            (a, b) => a.timestamp.localeCompare(b.timestamp) || a.id - b.id
          ),
        })
      )
      .sort(
        (a, b) =>
          a.interactions[0].timestamp.localeCompare(b.interactions[0].timestamp) ||
          a.interactions[0].id - b.interactions[0].id
      );
  }, [visibleInteractions]);
  const storedAnchorState = useMemo(
    () => loadConversationAnchor(conversationKey),
    [conversationKey]
  );
  // The "collapse all but the most recently active thread" default can only
  // be computed once real thread data has arrived. On a real page load this
  // component mounts (keyed by conversationKey/sceneId, per GameWindow.tsx)
  // the instant sceneId becomes truthy, while useSceneInteractions's
  // useInfiniteQuery is still in flight — so `groups` is empty on that first
  // render. A lazy useState initializer only ever sees that one, empty
  // render and never re-runs once real data lands, so the default silently
  // never applies. Instead: seed synchronously from storage if it exists
  // (and never let the async default fire on top of restored state), else
  // leave `collapsed` empty and let the effect below apply the default the
  // first time `groups` is actually populated. `defaultSeeded` guards that
  // effect so it only ever runs once per mount — the user's own subsequent
  // toggles (via toggleThread/bulk expand-collapse) are the only thing
  // allowed to change `collapsed` after that.
  const [collapsed, setCollapsed] = useState<Set<string>>(() =>
    storedAnchorState ? new Set(storedAnchorState.collapsed) : new Set()
  );
  const defaultSeeded = useRef(storedAnchorState !== null);
  useEffect(() => {
    if (defaultSeeded.current) return;
    if (groups.length === 0) return;
    defaultSeeded.current = true;
    if (groups.length <= 1) {
      setCollapsed(new Set());
      return;
    }
    const mostRecentKey = [...groups].sort((a, b) =>
      b.interactions[b.interactions.length - 1].timestamp.localeCompare(
        a.interactions[a.interactions.length - 1].timestamp
      )
    )[0].key;
    setCollapsed(new Set(groups.filter((g) => g.key !== mostRecentKey).map((g) => g.key)));
  }, [groups]);
  const [collapsedPoses, setCollapsedPoses] = useState<Set<number>>(new Set());
  // Optimistic mirror of "Mark conversation read" (#3759 spec section 7): the
  // server call is fire-and-forget, like markPosesRead's dwell-tracked path,
  // so unread badges are cleared locally immediately rather than waiting on
  // whatever next refetches `interactions` -- a pose's timestamp is stable and
  // ISO-8601-sortable (same string-compare convention `groups`/`chronologicalItems`
  // already use above), so "was this pose covered by the last mark-read click"
  // is just a string comparison against the snapshot boundary sent to the server.
  const [locallyReadBefore, setLocallyReadBefore] = useState<string | null>(null);
  const isEffectivelyUnread = (item: Interaction) =>
    Boolean(item.is_unread) && (locallyReadBefore === null || item.timestamp > locallyReadBefore);
  const handleMarkConversationRead = () => {
    if (interactions.length === 0) return;
    const before = interactions.reduce(
      (latest, item) => (item.timestamp > latest ? item.timestamp : latest),
      interactions[0].timestamp
    );
    setLocallyReadBefore(before);
    markConversationRead(conversationRef, before).catch((error: unknown) => {
      console.error('Failed to mark conversation read', error);
    });
  };
  const { observe } = usePoseReadTracking();
  const { preferences, update } = usePlayPreferences();
  const chronological = preferences.readerMode === 'chronological';
  const chronologicalItems = useMemo(
    () =>
      [...visibleInteractions].sort(
        (a, b) => a.timestamp.localeCompare(b.timestamp) || a.id - b.id
      ),
    [visibleInteractions]
  );
  const chronoParentRef = useRef<HTMLDivElement>(null);
  const chronoVirtualizer = useVirtualizer({
    count: chronologicalItems.length,
    getScrollElement: () => chronoParentRef.current,
    estimateSize: () => 160,
    overscan: 8,
  });

  // Shared read-merge-write so a collapse toggle never clobbers a
  // concurrently-saved anchor (and vice versa): both sides of this feature
  // write the same localStorage row, so each write re-reads whatever the
  // OTHER side most recently saved instead of layering over a stale
  // mount-time snapshot (`storedAnchorState` is only ever fresh at mount).
  //
  // `anchor`, when present, writes into whichever mode's own slot is
  // CURRENTLY ACTIVE (`anchors.threads` or `anchors.chronological`) --
  // Threads and Chronological "share content and read state ... but keep
  // their own anchor" (ratified Decision #2, #3759 review finding I5): a
  // single shared `anchor` field meant switching reader mode inherited (then
  // clobbered, on the next save) the OTHER mode's own remembered position.
  const persistAnchorState = (overrides: {
    anchor?: ReadingAnchor | null;
    collapsed?: string[];
  }) => {
    const current = loadConversationAnchor(conversationKey);
    const currentAnchors = current?.anchors ?? { threads: null, chronological: null };
    const nextAnchors =
      'anchor' in overrides
        ? {
            ...currentAnchors,
            [chronological ? 'chronological' : 'threads']: overrides.anchor ?? null,
          }
        : currentAnchors;
    saveConversationAnchor(conversationKey, {
      anchors: nextAnchors,
      collapsed: overrides.collapsed ?? current?.collapsed ?? [],
    });
  };
  // Gate the WRITE only (#3759 review finding I1) -- collapsing threads stays
  // allowed while reading a reference or a non-room conversation tab
  // (Decision #5 governs the STORED state, not the in-memory `collapsed`
  // React state above); it must just never corrupt someone ELSE's stored
  // row. Same two conditions the anchor-save paths below already gate on.
  const persistCollapsed = (next: Set<string>) => {
    if (readOnly || !persistAnchor) return;
    persistAnchorState({ collapsed: [...next] });
  };
  const toggleThread = (key: string) =>
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      persistCollapsed(next);
      return next;
    });
  const expandAllThreads = () => {
    const next = new Set<string>();
    setCollapsed(next);
    persistCollapsed(next);
  };
  const collapseAllThreads = () => {
    const next = new Set(groups.map((group) => group.key));
    setCollapsed(next);
    persistCollapsed(next);
  };
  const togglePose = (id: number) =>
    setCollapsedPoses((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // --- Reading-position anchors (#3759 Decision #3 / Wave 6) ---------------
  // The anchor identifies a pose (+ thread) and a pixel offset, never a raw
  // scrollTop -- so it survives resize, font/measure changes and
  // older-page-insertion, which all change *where* that same pose happens to
  // land on screen without changing *which pose* the reader should be
  // showing. `readOnlyRef`/`visibleInteractionsRef`/`collapsedRef` mirror the
  // latest render's values for the native (non-JSX) scroll listener below,
  // which is attached once per Threads-view session rather than
  // re-subscribed on every interaction/collapse change (re-subscribing would
  // risk dropping an in-flight debounce right when the user is mid-scroll).
  const rootRef = useRef<HTMLDivElement>(null);
  const readOnlyRef = useRef(readOnly);
  readOnlyRef.current = readOnly;
  const persistAnchorRef = useRef(persistAnchor);
  persistAnchorRef.current = persistAnchor;
  const visibleInteractionsRef = useRef(visibleInteractions);
  visibleInteractionsRef.current = visibleInteractions;
  const collapsedRef = useRef(collapsed);
  collapsedRef.current = collapsed;
  const conversationKeyRef = useRef(conversationKey);
  conversationKeyRef.current = conversationKey;

  // #3759 review finding I2: an anchor older than the default tail window is
  // the COMMON case, not an edge case -- before falling back to scrolling to
  // the bottom, check whether the anchored pose exists ANYWHERE in the full
  // `interactions` array (not just the currently-sliced tail window) and, if
  // so, widen the window to include it (a few poses of context above it too)
  // instead of jumping away. Shared with the deep-link target-seek effect
  // below (#3759 review finding C2), which needs the identical mechanism.
  const anchorRetryPendingRef = useRef(false);
  const widenWindowToInclude = (poseId: string): boolean => {
    const idx = interactions.findIndex((item) => String(item.id) === poseId);
    if (idx === -1) return false;
    const desiredStart = Math.max(0, idx - 5);
    if (desiredStart >= historyStart) return false; // already covered -- not the miss case
    setHistoryStartOverride(desiredStart);
    anchorRetryPendingRef.current = true;
    return true;
  };
  // Suppresses the scroll-triggered anchor SAVE the bottom-fallback's own
  // programmatic `scrollTop`/`scrollToEnd()` would otherwise fire (#3759
  // review finding I2) -- an unsuppressed fallback scroll reaches the
  // debounced save listeners below, which would persist the bottom pose as
  // the new anchor and destroy the user's actual saved place on the very
  // reload meant to restore it. Shared between both views since only one is
  // ever active (`chronological`) at a time.
  const suppressNextAnchorSaveRef = useRef(false);

  const restoreThreadsAnchor = () => {
    const stored = loadConversationAnchor(conversationKeyRef.current);
    const anchor = stored?.anchors?.threads;
    if (!anchor) return;
    const container = findScrollContainer(rootRef.current);
    if (!container) return;
    const target = container.querySelector<HTMLElement>(`[data-pose-id="${anchor.poseId}"]`);
    if (!target) {
      // Best-effort miss: the anchored pose isn't in the currently loaded/
      // expanded set (e.g. it's inside a collapsed thread, or on an older
      // history page not yet fetched). Widen the window first (I2, above);
      // only fall all the way back to the bottom once the pose is confirmed
      // genuinely absent from `interactions` altogether.
      if (widenWindowToInclude(anchor.poseId)) return;
      // GameWindow.tsx no longer applies its own scroll-to-bottom fallback
      // once this scene has ANY persisted anchor (see its own bypass
      // condition) -- so restoring that fallback here is what keeps a
      // genuine miss from silently stranding the reader at the very top
      // instead (#3759 review finding I3).
      suppressNextAnchorSaveRef.current = true;
      container.scrollTop = container.scrollHeight;
      return;
    }
    const targetTop = target.getBoundingClientRect().top - container.getBoundingClientRect().top;
    container.scrollTop += targetTop - anchor.offsetPx;
  };

  const restoreChronoAnchor = () => {
    const stored = loadConversationAnchor(conversationKeyRef.current);
    const anchor = stored?.anchors?.chronological;
    if (!anchor) return;
    const idx = chronologicalItems.findIndex((item) => String(item.id) === anchor.poseId);
    if (idx === -1) {
      // Same widen-before-fallback reasoning as restoreThreadsAnchor's own
      // miss branch above (#3759 review finding I2).
      if (widenWindowToInclude(anchor.poseId)) return;
      // Best-effort miss, same reasoning as restoreThreadsAnchor's fallback
      // above (#3759 review finding I3).
      suppressNextAnchorSaveRef.current = true;
      chronoVirtualizer.scrollToEnd();
      return;
    }
    // Deliberately reduced scope (see file-level note above the
    // Chronological branch below): restores to the nearest loaded index at
    // the top of the viewport, not the exact recorded pixel offset.
    chronoVirtualizer.scrollToIndex(idx, { align: 'start' });
  };

  const restoreAnchor = () => {
    if (chronological) restoreChronoAnchor();
    else restoreThreadsAnchor();
  };

  // Retries a restore once a widen (I2, above) has actually taken effect --
  // `widenWindowToInclude` only schedules the wider `historyStartOverride`;
  // the pose isn't mounted (and thus findable) until the resulting re-render
  // commits, which is exactly when `historyStart` changes.
  useEffect(() => {
    if (!anchorRetryPendingRef.current) return;
    anchorRetryPendingRef.current = false;
    restoreAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyStart]);

  // Effect A: initial restore, once real pose data has arrived. Mirrors the
  // `defaultSeeded` pattern above -- this component can mount (keyed by
  // conversationKey/sceneId) before its interactions query resolves, so a
  // lazy useState initializer would only ever see that first empty render.
  // Guarded to fire at most once per mount so a later, unrelated arrival of
  // new poses doesn't yank the reader back to the anchor while the user is
  // reading elsewhere.
  const restoreSeeded = useRef(false);
  useEffect(() => {
    if (restoreSeeded.current) return;
    if (readOnly) return; // never restore into a historical reference view
    if (visibleInteractions.length === 0) return;
    restoreSeeded.current = true;
    restoreAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, visibleInteractions.length]);

  // Effect B: "Return to live" (#3759 Decision #5). Re-applies the anchor
  // specifically on the readOnly:true -> false transition, regardless of
  // whether Effect A already ran -- GameWindow reuses this same component
  // instance across the reference/live boundary (same `conversationKey`), so
  // without this, returning to live would just leave the reader wherever
  // reading the historical reference left it.
  const prevReadOnlyRef = useRef(readOnly);
  useEffect(() => {
    const wasReadOnly = prevReadOnlyRef.current;
    prevReadOnlyRef.current = readOnly;
    if (wasReadOnly && !readOnly) restoreAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly]);

  // Effect C: font/measure-change survival (#3759 Acceptance A08). A
  // proseSize/proseFamily/measure change doesn't move which pose the user
  // was reading -- only where it lands on screen -- so simply re-running the
  // same restore whenever one of these changes keeps the anchored pose in
  // the same relative viewport position after the change.
  //
  // Deferred via requestAnimationFrame rather than measured synchronously
  // (#3759 review finding I1): in the real component tree, `DisplaySettings`
  // (which applies these prefs as a CSS custom property on
  // `document.documentElement`) is a SIBLING rendered after this reader
  // (GameLayout.tsx: `center` before `sidebar`). React flushes passive
  // effects in tree order, so this effect's synchronous body would run
  // BEFORE `DisplaySettings`'s own effect has actually applied the new CSS
  // variable -- measuring the OLD layout and computing a near-zero,
  // effectively-a-no-op delta. rAF fires after all of this commit's passive
  // effects (and the browser's/jsdom's next paint), by which point the CSS
  // variable is guaranteed to have been applied regardless of which
  // component's effect happened to run first.
  useEffect(() => {
    // Also gated on persistAnchor (#3759 review finding, second pass): this
    // reader instance doesn't own the room's persisted anchor while a
    // non-room conversation tab is active (see the save-side guards above),
    // so re-restoring here would look up the ROOM anchor, fail to find its
    // pose in this tab's narrower interaction set, and fall into the I3
    // miss-fallback (scrollTop = scrollHeight) -- jumping this tab's feed to
    // the bottom on every preference change, a behavior that didn't exist
    // before the I3 fallback was added (a miss used to be a silent no-op).
    if (readOnly || !persistAnchorRef.current) return;
    const rafId = requestAnimationFrame(() => {
      restoreAnchor();
    });
    return () => cancelAnimationFrame(rafId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preferences.proseSize, preferences.proseFamily, preferences.measure]);

  // --- Deep-link target seek (#3759 review finding C2) ----------------------
  // `PlayContextView` hands the reference reader a fixed +-25-pose window
  // around the opened pose, but this reader's own tail-slice
  // (`historyStart`) always shows only the LAST `INITIAL_PAGE_SIZE` poses of
  // whatever window it's given -- for a target sitting anywhere earlier than
  // that (the common case: a search result or "Recent conversations" row
  // rarely lands in the newest 20 poses of its own +-25 window), the
  // tail-slice alone renders everything BUT the pose the user actually
  // opened. Reuses `widenWindowToInclude` (I2, above) to seed the window,
  // then scrolls to and briefly highlights the target once its row mounts.
  // `targetSeekDoneRef` guards this so it runs once per target -- a NEW
  // target (switching between reference entries without unmounting, e.g. two
  // search results in the same scene) resets it because the ref stores the
  // id it last completed, not just a boolean.
  const targetSeekDoneRef = useRef<string | null>(null);
  const [highlightedPoseId, setHighlightedPoseId] = useState<string | null>(null);
  useEffect(() => {
    if (!targetPoseId) return;
    if (targetSeekDoneRef.current === targetPoseId) return;
    const idx = interactions.findIndex((item) => String(item.id) === targetPoseId);
    if (idx === -1) return; // not in the loaded window at all -- nothing to seek to
    const desiredStart = Math.max(0, idx - 5);
    if (historyStart > desiredStart) {
      setHistoryStartOverride(desiredStart);
      return; // the re-render with the widened window re-runs this effect
    }
    const targetEl = rootRef.current?.querySelector<HTMLElement>(
      `[data-pose-id="${targetPoseId}"]`
    );
    if (!targetEl) return; // not mounted on this pass yet (e.g. inside a collapsed thread)
    targetSeekDoneRef.current = targetPoseId;
    targetEl.scrollIntoView({ block: 'center' });
    setHighlightedPoseId(targetPoseId);
    const timeout = setTimeout(() => setHighlightedPoseId(null), 2000);
    return () => clearTimeout(timeout);
  }, [targetPoseId, interactions, historyStart]);

  // Threads-view scroll listener (#3759 review finding C1): attached at
  // `document` with `capture: true` rather than resolved-once onto a
  // specific ancestor element. Native 'scroll' events don't bubble, but DO
  // propagate during the capture phase, so this single listener sees a
  // scroll on ANY descendant scrollable ancestor -- including
  // GameWindow.tsx's real `feedScrollRef` div -- without this reader ever
  // needing to pre-resolve which element that is.
  //
  // The original version of this effect called `findScrollContainer` once,
  // at mount, and permanently gave up if it returned `null` -- which it
  // always does on a cold page load: this component mounts (per
  // GameWindow.tsx) the instant `sceneId` is known, while
  // `useSceneInteractions`'s query is still in flight, so nothing has
  // rendered/overflowed yet. No listener was ever attached for the life of
  // that mount, so the entire save half of the feature was dead in
  // production despite passing tests (the tests' global
  // scrollHeight/clientHeight stub made a container resolve unconditionally,
  // masking this). Listening at `document` sidesteps needing to resolve
  // anything ahead of time at all.
  useEffect(() => {
    if (chronological) return;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const handleScroll = (event: Event) => {
      const container = event.target;
      if (!(container instanceof HTMLElement) || !rootRef.current) return;
      if (!container.contains(rootRef.current)) return;
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(() => {
        // never persist a reference-mode scroll, or one made while a
        // different conversation tab is active (#3759 review findings I3/I4)
        if (readOnlyRef.current || !persistAnchorRef.current) return;
        // never persist the anchor-miss bottom-fallback's OWN scroll (#3759
        // review finding I2) -- that would destroy the real anchor it just
        // failed to find, instead of leaving it alone for the next attempt.
        if (suppressNextAnchorSaveRef.current) {
          suppressNextAnchorSaveRef.current = false;
          return;
        }
        const found = findTopVisiblePoseId(container);
        if (!found) return;
        const threadId =
          visibleInteractionsRef.current.find((item) => String(item.id) === found.poseId)
            ?.thread_id ?? null;
        persistAnchorState({
          anchor: { poseId: found.poseId, threadId, offsetPx: found.offsetPx },
          collapsed: [...collapsedRef.current],
        });
      }, 300);
    };
    document.addEventListener('scroll', handleScroll, { capture: true, passive: true });
    return () => {
      document.removeEventListener('scroll', handleScroll, true);
      if (timeout) clearTimeout(timeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chronological]);

  // Chronological-view scroll handler: this view already owns its own scroll
  // container (`chronoParentRef`), so this is a plain onScroll prop rather
  // than a native listener -- no ancestor lookup needed.
  const chronoScrollTimeout = useRef<ReturnType<typeof setTimeout>>();
  const handleChronoScroll = () => {
    if (chronoScrollTimeout.current) clearTimeout(chronoScrollTimeout.current);
    chronoScrollTimeout.current = setTimeout(() => {
      if (readOnly || !persistAnchor) return;
      // Same anchor-miss-fallback suppression as the Threads-view listener
      // above (#3759 review finding I2).
      if (suppressNextAnchorSaveRef.current) {
        suppressNextAnchorSaveRef.current = false;
        return;
      }
      const container = chronoParentRef.current;
      if (!container) return;
      const found = findTopVisiblePoseId(container);
      if (!found) return;
      const threadId =
        visibleInteractions.find((item) => String(item.id) === found.poseId)?.thread_id ?? null;
      persistAnchorState({
        anchor: { poseId: found.poseId, threadId, offsetPx: found.offsetPx },
        collapsed: [...collapsed],
      });
    }, 300);
  };
  useEffect(
    () => () => {
      if (chronoScrollTimeout.current) clearTimeout(chronoScrollTimeout.current);
    },
    []
  );

  return (
    <div
      ref={rootRef}
      className="min-h-0 flex-1 [&_.text-sm]:text-[length:var(--play-prose-size,14px)]"
      aria-label="Story reader"
      style={{
        fontSize: 'var(--play-prose-size, 14px)',
        fontFamily: 'var(--play-prose-family, ui-sans-serif)',
      }}
    >
      <div className="mx-auto w-full max-w-[var(--play-reading-measure,90ch)] space-y-3 px-4 py-4">
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            {groups.length
              ? `${groups.length} conversation${groups.length === 1 ? '' : 's'}`
              : 'New conversation'}
          </span>
          <div className="flex gap-2">
            {groups.length > 0 && (
              <>
                <button className="underline" onClick={expandAllThreads}>
                  Expand loaded threads
                </button>
                <button className="underline" onClick={collapseAllThreads}>
                  Collapse loaded threads
                </button>
              </>
            )}
            {interactions.length > 0 && (
              <button className="underline" onClick={handleMarkConversationRead}>
                Mark conversation read
              </button>
            )}
            <button
              className="underline"
              aria-pressed={chronological}
              onClick={() => update({ readerMode: chronological ? 'threads' : 'chronological' })}
            >
              {chronological ? 'Threads' : 'Chronological'}
            </button>
          </div>
        </div>
        {chronological &&
          (chronologicalItems.length === 0 ? (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <MessageCircle className="mx-auto h-6 w-6 text-muted-foreground" />
              <h2 className="mt-2 font-serif text-xl">Begin the scene</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Write the next part of the story below.
              </p>
            </div>
          ) : (
            // Anchor restore here is deliberately reduced-scope (#3759 Wave
            // 6): it calls chronoVirtualizer.scrollToIndex (see
            // restoreChronoAnchor above) rather than reproducing Threads
            // view's exact-pixel-offset restore. A virtualized list can't
            // measure an off-screen row until it's mounted, so landing on
            // the precise recorded offsetPx would need a further
            // measure/re-scroll pass once the target row renders; the
            // simpler nearest-index landing was judged good enough for this
            // less-used view. A follow-up wanting pixel parity here would
            // add that second pass once the target row's ref resolves.
            <div
              ref={chronoParentRef}
              onScroll={handleChronoScroll}
              data-testid="chrono-scroll-container"
              // Explicit, bounded height (#3759 review Fix round 1 CRITICAL) --
              // NOT `flex-1` (tried in Wave 8, reverted here): `flex-1` only
              // resolves against a flex *parent*, and neither GameWindow.tsx's
              // feed div nor this reader's own root/wrapper divs are
              // `display: flex` from THIS element's perspective, so the class
              // was inert -- the container's height collapsed to `auto`
              // (sized to content), `overflow-y-auto` never engaged,
              // `onScroll` never fired a real scroll, and
              // `@tanstack/react-virtual`'s `getScrollElement` saw a viewport
              // covering all content, defeating Task 10's windowing
              // entirely. Every pre-existing test still passed because they
              // stub `scrollHeight`/`clientHeight` directly on this element
              // and fire synthetic scroll events -- the exact masking
              // pattern documented on the Threads-view listener below
              // (Wave 6's original C1), now on its second occurrence.
              style={{ height: '70vh', overflow: 'auto' }}
            >
              <div style={{ height: chronoVirtualizer.getTotalSize(), position: 'relative' }}>
                {chronoVirtualizer.getVirtualItems().map((virtualRow) => {
                  const item = chronologicalItems[virtualRow.index];
                  const poseCollapsed = collapsedPoses.has(item.id);
                  return (
                    <div
                      key={item.id}
                      data-index={virtualRow.index}
                      ref={chronoVirtualizer.measureElement}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                    >
                      <PoseReadTarget
                        pose={{ id: item.id, timestamp: item.timestamp }}
                        observe={observe}
                        highlighted={String(item.id) === highlightedPoseId}
                      >
                        <p className="text-xs text-muted-foreground">
                          {item.thread_id ? 'In a thread' : 'Standalone'}
                        </p>
                        {poseCollapsed ? (
                          <article
                            className="mx-2 rounded border border-dashed px-3 py-2 text-sm"
                            data-testid={`collapsed-pose-${item.id}`}
                          >
                            <strong>{item.persona.name}</strong>
                            <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-muted-foreground">
                              {item.content}
                            </p>
                            <button
                              type="button"
                              className="mt-1 min-h-9 underline"
                              onClick={() => togglePose(item.id)}
                            >
                              Show full pose
                            </button>
                          </article>
                        ) : (
                          <SceneMessages
                            sceneId={sceneId}
                            filteredInteractions={[item]}
                            onAvatarClick={onAvatarClick}
                            onAddTarget={onAddTarget}
                            onAttachAction={onAttachAction}
                            readOnly={readOnly}
                          />
                        )}
                      </PoseReadTarget>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        {!chronological &&
          (groups.length === 0 ? (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <MessageCircle className="mx-auto h-6 w-6 text-muted-foreground" />
              <h2 className="mt-2 font-serif text-xl">Begin the scene</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Write the next part of the story below.
              </p>
            </div>
          ) : (
            groups.map((group) => {
              const root = group.interactions[0];
              const isCollapsed = collapsed.has(group.key);
              const unread = group.interactions.filter(isEffectivelyUnread).length;
              return (
                <section
                  key={group.key}
                  className="overflow-hidden rounded-lg border bg-card/60"
                  data-thread-id={group.key}
                >
                  <button
                    type="button"
                    className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent/40"
                    aria-expanded={!isCollapsed}
                    aria-controls={`thread-${group.key}`}
                    onClick={() => toggleThread(group.key)}
                  >
                    {isCollapsed ? (
                      <ChevronRight className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {root?.persona.name ?? 'Conversation'}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {group.interactions.length}{' '}
                      {group.interactions.length === 1 ? 'pose' : 'poses'}
                    </span>
                    {unread > 0 && (
                      <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] text-primary-foreground">
                        {unread} new
                      </span>
                    )}
                  </button>
                  {!isCollapsed && (
                    <div id={`thread-${group.key}`} className="border-t px-2 py-2">
                      {group.interactions.map((item) => {
                        const poseCollapsed = collapsedPoses.has(item.id);
                        return (
                          <PoseReadTarget
                            key={`pose-${item.id}`}
                            pose={{ id: item.id, timestamp: item.timestamp }}
                            observe={observe}
                            highlighted={String(item.id) === highlightedPoseId}
                          >
                            {poseCollapsed ? (
                              <article
                                className="mx-2 rounded border border-dashed px-3 py-2 text-sm"
                                data-testid={`collapsed-pose-${item.id}`}
                              >
                                <strong>{item.persona.name}</strong>
                                <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-muted-foreground">
                                  {item.content}
                                </p>
                                <button
                                  type="button"
                                  className="mt-1 min-h-9 underline"
                                  onClick={() => togglePose(item.id)}
                                >
                                  Show full pose
                                </button>
                              </article>
                            ) : (
                              <>
                                <SceneMessages
                                  sceneId={sceneId}
                                  filteredInteractions={[item]}
                                  onAvatarClick={onAvatarClick}
                                  onAddTarget={onAddTarget}
                                  onAttachAction={onAttachAction}
                                  readOnly={readOnly}
                                />
                                <div className="flex items-center justify-end gap-2 px-2 text-xs text-muted-foreground">
                                  <button
                                    type="button"
                                    className="inline-flex min-h-9 items-center gap-1 underline"
                                    onClick={() => togglePose(item.id)}
                                  >
                                    Show less
                                  </button>
                                  {onReply && !readOnly && (
                                    <button
                                      type="button"
                                      className="inline-flex min-h-9 items-center gap-1 underline"
                                      onClick={() => onReply(item)}
                                    >
                                      <Reply className="h-3 w-3" /> Reply
                                    </button>
                                  )}
                                </div>
                              </>
                            )}
                          </PoseReadTarget>
                        );
                      })}
                    </div>
                  )}
                </section>
              );
            })
          ))}
        {(historyStart > 0 || hasNextPage) && (
          <div className="flex gap-2">
            {historyStart > 0 && (
              <button
                type="button"
                onClick={() =>
                  setHistoryStartOverride(Math.max(0, historyStart - INITIAL_PAGE_SIZE))
                }
                className="flex-1 rounded border px-3 py-2 text-sm"
              >
                Load earlier history
              </button>
            )}
            {historyStart < Math.max(0, interactions.length - INITIAL_PAGE_SIZE) && (
              <button
                type="button"
                onClick={() =>
                  setHistoryStartOverride(Math.max(0, interactions.length - INITIAL_PAGE_SIZE))
                }
                className="rounded border px-3 py-2 text-sm"
              >
                Jump to latest
              </button>
            )}
            {historyStart === 0 && hasNextPage && (
              <button
                type="button"
                onClick={fetchNextPage}
                className="flex-1 rounded border px-3 py-2 text-sm"
              >
                Load earlier history
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
