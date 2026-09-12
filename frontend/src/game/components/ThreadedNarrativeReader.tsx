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
import { excerptOf } from '@/lib/formatParser';
import { useViewerPersonaId } from '@/roster/persona';
import { replyReachability, type ViewerVenue } from '@/scenes/replyReachability';

// #3759 Wave 9 (demo-fidelity review F1/F2): was `INITIAL_PAGE_SIZE`, a flat
// whole-list tail-slice size -- repurposed as the default number of a single
// EXPANDED thread's own poses shown at once (see `threadWindows`/
// `resolveThreadWindow` below). Renamed because its job changed: nothing
// windows the flat list anymore, only individual threads.
const THREAD_PAGE_SIZE = 20;

/**
 * #3759 Wave 9 review finding F4: the flat, non-chip pose-context label the
 * spec's anti-reinvention ledger says to KEEP, not replace with per-pose
 * parent-chip persistence -- "Opening pose" for a REAL thread's own root
 * pose, "Standalone" for an ordinary un-replied pose. Shared between Threads
 * view (where `rootPose` is already in scope as `group.interactions[0]`) and
 * Chronological view (where it's looked up via `groupByKey`, below) so both
 * views render identical labels for the identical pose.
 *
 * #3759 Wave 9 fix round 1 Minor M-1: `item.thread_id` (not merely "is this
 * the group's own root") gates "Opening pose" -- an ordinary, un-replied
 * pose (`thread_id === null`, keyed `legacy:${id}` in `groups`) is trivially
 * its own group's root by construction, but "Opening pose" asserts a THREAD
 * that doesn't exist for it. "Standalone" (matching Chronological's own
 * pre-existing phrasing for this exact case) is correct for both views.
 *
 * #3787 Task 7: the third case this used to cover -- an ordinary reply deep
 * in a real thread -- used to return `Reply in <title>` as a stand-in for
 * per-pose parent data that didn't exist yet (that branch's own doc comment
 * said so). It does now (`Interaction.reply_to`, #3787 Tasks 1-2), and
 * `PoseUnit.tsx`'s parent chip ("Answering “...”") renders it
 * directly on the pose itself -- a real quote of what was actually answered,
 * not a derived thread title -- so this label goes empty for that case
 * rather than duplicating weaker information beside the chip.
 */
function poseRoleLabel(item: Interaction, rootPose: Interaction | undefined): string {
  if (!item.thread_id) return 'Standalone';
  if (!rootPose || rootPose.id === item.id) return 'Opening pose';
  return '';
}

/**
 * The involved-viewer treatment (#3787 demo Screen 1): a row whose
 * `target_persona_ids` names the viewer's own active persona gets a distinct,
 * highlighted restatement of the SAME (already per-viewer-rendered) content
 * plus a prominent "Answer this" control, instead of the ordinary quiet
 * Reply link every other row keeps. One phrasing for all five row kinds the
 * spec names (combat outcome, NPC action, social check, prose tag, whisper)
 * -- this is gated purely on `target_persona_ids`, never on `item.mode`, so
 * it needs no per-mode copy to maintain.
 */
function isInvolvingViewer(item: Interaction, viewerPersonaId: number | null): boolean {
  return viewerPersonaId != null && item.target_persona_ids.includes(viewerPersonaId);
}

/**
 * The reply/answer control for one pose, covering both demo Screen 1/2 (an
 * ordinary or prominent control that opens the composer on this row) and
 * Screen 3 (the SAME control rendered disabled, with the refusal shown
 * before the click, when `replyReachability` finds the viewer's current
 * venue cannot reach this row). Shared between the legacy-standalone and
 * real-thread render branches below so the two never drift.
 */
function ReplyControl({
  item,
  onReply,
  involved,
  venue,
}: {
  item: Interaction;
  onReply: (interaction: Interaction) => void;
  involved: boolean;
  venue: ViewerVenue;
}) {
  const refusal = replyReachability(item, venue);
  const label = involved ? 'Answer this' : 'Reply';
  if (!refusal.reachable) {
    return (
      <div
        className="flex flex-col items-end gap-1"
        data-testid={`reply-refusal-${item.id}`}
        role="status"
        aria-live="polite"
      >
        <button
          type="button"
          disabled
          className="inline-flex min-h-9 cursor-not-allowed items-center gap-1 text-muted-foreground line-through opacity-70"
        >
          {!involved && <Reply className="h-3 w-3" />} {label}
        </button>
        <p className="max-w-xs text-right text-xs">
          <strong className="text-destructive">{refusal.reason}</strong>{' '}
          {refusal.hint && <span className="text-muted-foreground">{refusal.hint}</span>}
        </p>
      </div>
    );
  }
  return (
    <button
      type="button"
      className={
        involved
          ? 'inline-flex min-h-9 items-center gap-1 rounded bg-primary px-2 py-1 font-semibold text-primary-foreground'
          : 'inline-flex min-h-9 items-center gap-1 underline'
      }
      data-testid={involved ? `answer-this-${item.id}` : undefined}
      onClick={() => onReply(item)}
    >
      {!involved && <Reply className="h-3 w-3" />} {label}
    </button>
  );
}

/**
 * The marked treatment for a row that names the viewer (demo Screen 1's
 * `.involves`): the amber-railed box the involved viewer reads the row IN,
 * wrapping the pose's own ordinary rendering rather than following it.
 *
 * #3787 final review D1: this used to render `item.content` itself, directly
 * after the same pose's own `<SceneMessages>` render, so the involved viewer
 * read the identical sentence twice in a row. The demo showed that line twice
 * as a SIDE-BY-SIDE device explaining what two different viewers see, never as
 * one viewer reading it twice. So the involved viewer gets the amber treatment
 * INSTEAD of the plain bubble: `children` is the pose's own per-viewer content
 * rendering, unchanged and rendered exactly once, with the label above it and
 * the prominent "Answer this" control below. Everyone else is untouched.
 *
 * Wrapping rather than restating is also what keeps the row whole: the pose's
 * own rendering carries the persona name, the parent chip, reactions and the
 * action-link affordances, none of which a restatement of `item.content` ever
 * had. Nothing here re-derives an actor or a different sentence.
 */
function InvolvementFlag({
  item,
  onReply,
  readOnly,
  venue,
  children,
}: {
  item: Interaction;
  onReply?: (interaction: Interaction) => void;
  readOnly: boolean;
  venue: ViewerVenue;
  children: ReactNode;
}) {
  return (
    <div
      className="mt-1 rounded-r-lg border-l-4 border-amber-500 bg-amber-500/10 px-3 py-2"
      data-testid={`involvement-mark-${item.id}`}
      role="status"
      aria-live="polite"
    >
      <span className="block text-xs font-semibold uppercase tracking-wide text-amber-600">
        This happened to you
      </span>
      {children}
      {onReply && !readOnly && (
        <div className="mt-1 flex justify-end">
          <ReplyControl item={item} onReply={onReply} involved venue={venue} />
        </div>
      )}
    </div>
  );
}

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
   * window around this pose, but a big thread within that window still only
   * shows its own default per-thread tail (`THREAD_PAGE_SIZE`, #3759 Wave 9
   * F1/F2) -- for a target sitting earlier than that, the default window
   * alone renders everything BUT the pose the user actually opened. When set
   * and present in `interactions`, the reader widens that thread's OWN
   * `threadWindows` entry to include it (uncollapsing the thread too, if
   * needed), then scrolls to and briefly highlights its `[data-pose-id]`
   * element once mounted. Absent in live mode, where the existing
   * per-thread default is unaffected.
   */
  targetPoseId?: string;
  /**
   * The viewer's current drafting venue (#3787 Screen 3, the pre-emptive
   * reply refusal) -- the same values `GamePage.tsx` already computes and
   * threads to `CommandInput` (`isAtPlace`/`currentPlaceId`), passed one hop
   * further by `GameWindow.tsx` rather than re-derived here. Omitted
   * (standalone/test/reference callers) defaults to "in the room", so every
   * row reads reachable -- the permissive default `replyReachability` itself
   * uses when `isAtPlace` is false.
   */
  isAtPlace?: boolean;
  currentPlaceId?: number | null;
  /** Human-readable current place name, for the refusal's hint text only. */
  currentPlaceName?: string | null;
}

interface Group {
  key: string;
  interactions: Interaction[];
}

/**
 * A single thread's own per-thread pose window (#3759 Wave 9 F1/F2),
 * replacing the old flat, whole-list `historyStartOverride`. `start`/`end`
 * are indices into that thread's OWN `group.interactions` (its full pose
 * list, not the whole conversation) -- both are always clamped against the
 * group's current length before use (see `resolveThreadWindow`), so a stale
 * entry from a differently-sized `interactions` array (e.g. carried over
 * from reference mode) can never index out of bounds; see the render-time
 * reset below for why a stale entry is cleared outright rather than relying
 * on that clamp alone.
 */
interface ThreadWindow {
  start: number;
  end: number;
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
  isAtPlace = false,
  currentPlaceId = null,
  currentPlaceName = null,
}: ThreadedNarrativeReaderProps) {
  // #3787 -- resolved the SAME way PoseUnit.tsx resolves its own self-pose
  // guard (no second source of truth): drives the involvement mark (Screen
  // 1) below.
  const viewerPersonaId = useViewerPersonaId();
  const viewerVenue: ViewerVenue = useMemo(
    () => ({ isAtPlace, currentPlaceId, currentPlaceName }),
    [isAtPlace, currentPlaceId, currentPlaceName]
  );
  // #3787 -- resolves `interaction.reply_to` (an `{id, timestamp}` thread
  // selector, not the parent's content) to the parent Interaction for
  // PoseUnit's parent chip. Built once from the full loaded `interactions`
  // array (not a windowed/filtered slice), so a thread's own reply can quote
  // a parent sitting outside its currently-shown window.
  const interactionsById = useMemo(
    () => new Map(interactions.map((item) => [item.id, item])),
    [interactions]
  );
  // #3759 Wave 9 (F1/F2): replaces the old flat, whole-list
  // `historyStartOverride` -- one window per THREAD (keyed by `group.key`)
  // instead of one for the whole list. See `ThreadWindow`'s own doc comment
  // above and `resolveThreadWindow` below for how an absent entry (the
  // common case) defaults.
  const [threadWindows, setThreadWindows] = useState<Record<string, ThreadWindow>>({});
  // Declared here (rather than down in the deep-link seek section below,
  // where it's actually used) because the render-time reset immediately
  // below needs to clear it -- see that block's own comment.
  const targetSeekDoneRef = useRef<string | null>(null);
  // #3759 review finding, minor fold-in (Fix round 1: converted from a
  // useEffect to a render-time state adjustment -- see why below):
  // `threadWindows` is component-local, live-feed per-thread window state.
  // Entering/leaving reference mode reuses this SAME component instance when
  // the scene matches (Decision #5), but a reference's `interactions` prop
  // is a completely different (smaller, fixed +-25-pose window) array than
  // the live feed's -- so is every one of its per-thread `group.interactions`
  // arrays. Reset on every ACTUAL readOnly transition (never on mount, where
  // there is nothing stale to clear).
  //
  // #3759 Wave 9 open decision (documented per the wave brief): unlike the
  // OLD flat `historyStartOverride` (a single index into the whole list,
  // where `slice(-shown)` degraded gracefully to "show everything" if
  // `shown` ever exceeded the new array's length), `threadWindows` stores
  // explicit `{ start, end }` INDICES per thread key. If a thread key
  // happened to collide between reference and live mode (e.g. the same
  // `thread_id` genuinely exists in both, as it would for the very thread a
  // reference deep-link opened), reusing a stale `{ start: 0, end: 25 }`
  // entry against a much larger live `group.interactions` would silently
  // show that thread's OLDEST 25 poses instead of its most recent -- a real,
  // silently-wrong slice, not a graceful degrade. `expandedKeys` (the
  // thread-expand Set, just below) is NOT reset the same way: a stale
  // expanded/collapsed entry on a colliding key is a minor "wrong thread
  // defaulted open" UX quirk, never a wrong SET of rendered poses, so it's
  // left as pre-existing, out-of-scope behavior. `threadWindows` doesn't get
  // that same benefit of the doubt -- reset it.
  //
  // A `useEffect`-based reset (the original version of this fix, back when
  // this was `historyStartOverride`) raced Effect B ("Return to live") and
  // the C2 seek effect's OWN success path: both scroll the DOM directly
  // WITHOUT calling `setThreadWindows` themselves, so "last setState call in
  // the same commit wins" never applied to them -- the reset's effect still
  // fired and re-rendered to the default window on the NEXT tick,
  // unmounting whatever they'd just scrolled to. Adjusting state during
  // rendering (comparing the prop against a STATE-held previous value,
  // React's own documented pattern for this) commits the narrowed window in
  // the SAME render Effect B/the seek effect will read when their OWN
  // effects run after this commit -- not one render later.
  //
  // Also resets `targetSeekDoneRef` (#3759 review Fix round 1: re-opening
  // the identical deep link after "Return to live" was a no-op on the same
  // scene, since no remount occurs and the ref still held the old pose id)
  // for the same reason: it must land in the SAME render the seek effect
  // will next observe, not a render later.
  const [prevReadOnlyForReset, setPrevReadOnlyForReset] = useState(readOnly);
  if (readOnly !== prevReadOnlyForReset) {
    setPrevReadOnlyForReset(readOnly);
    setThreadWindows({});
    // A ref mutation during render is safe HERE specifically because it's
    // idempotent (always assigning the same literal `null`, never a
    // render-dependent value) -- React may discard and redo this render pass
    // (StrictMode double-invoke, concurrent rendering) without changing the
    // outcome. A future edit that made this conditional or assigned
    // something other than a constant (e.g. `targetPoseId`) would NOT be
    // safe the same way and could break silently under those same
    // conditions -- keep this assignment idempotent.
    targetSeekDoneRef.current = null;
  }
  // #3759 Wave 9 (F1): grouped from the FULL `interactions` array, not a
  // windowed slice -- every thread with at least one pose gets a header row,
  // always, matching the demo (the review's F1 finding: the old flat
  // `historyStart` tail-slice, taken BEFORE grouping, silently hid any
  // thread whose most recent pose fell outside it -- not even a collapsed
  // header rendered). Per-thread windowing (`resolveThreadWindow`, below)
  // now owns limiting how much of an EXPANDED thread's own poses render.
  const groups = useMemo(() => {
    const grouped = new Map<string, Interaction[]>();
    for (const interaction of interactions) {
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
  }, [interactions]);
  // #3759 Wave 9 fix-round-1 re-review Minor fold-in: a `legacy:` group is a
  // single un-replied pose (I-5, above), not a "conversation" -- excluded
  // from the toolbar's conversation count, the bulk expand/collapse-all
  // targets, and `mostRecentGroupKey` (below), so "Latest activity" and the
  // default-collapse seed always land on an actual thread instead of
  // silently no-op'ing when the chronologically-last pose happens to be
  // standalone narration.
  const realThreadGroups = useMemo(
    () => groups.filter((group) => !group.key.startsWith('legacy:')),
    [groups]
  );
  // Shared by the default-collapse effect (below) and the "Latest activity"
  // toolbar button (#3759 Wave 9 F5) -- both need "which thread's last pose
  // is the most recent," so this is computed once rather than duplicated.
  const mostRecentGroupKey = useMemo(() => {
    if (realThreadGroups.length === 0) return null;
    return [...realThreadGroups].sort((a, b) =>
      b.interactions[b.interactions.length - 1].timestamp.localeCompare(
        a.interactions[a.interactions.length - 1].timestamp
      )
    )[0].key;
  }, [realThreadGroups]);
  // Looked up by Chronological view's role-label rendering (#3759 Wave 9 F4)
  // to find a pose's thread root without a linear scan of `groups` per pose.
  const groupByKey = useMemo(() => new Map(groups.map((group) => [group.key, group])), [groups]);
  /**
   * Resolves a thread's currently-shown window, clamped against its OWN
   * current pose count (#3759 Wave 9 F1/F2). Absent from `threadWindows`
   * (the common case -- untouched by any earlier/later click or widen) means
   * "show the default tail" and is recomputed fresh from the group's CURRENT
   * length every render, so it always reaches the thread's true latest pose
   * without needing any reset when new poses arrive live.
   */
  const resolveThreadWindow = (group: Group): ThreadWindow => {
    const length = group.interactions.length;
    const stored = threadWindows[group.key];
    if (!stored) return { start: Math.max(0, length - THREAD_PAGE_SIZE), end: length };
    return { start: Math.min(stored.start, length), end: Math.min(stored.end, length) };
  };
  const storedAnchorState = useMemo(
    () => loadConversationAnchor(conversationKey),
    [conversationKey]
  );
  // #3759 Wave 9 fix round 1 finding I-4: this is `expandedKeys` -- an
  // OPT-IN set of expanded thread keys -- not the `collapsed` opt-OUT set
  // this component used through the rest of Wave 9. `groups` now always
  // holds every thread the reader has ever seen (F1), and that set can grow
  // AFTER mount (a `fetchNextPage` revealing older threads; a persisted
  // storage row written before this wave, which only ever named ~20 keys
  // back when `groups` itself was capped at 20). An opt-OUT `collapsed` set
  // means any key that set doesn't already know about defaults to EXPANDED
  // -- exactly backwards from "collapsed by default except the most
  // recently active thread," and silently so, since nothing about a newly-
  // revealed thread ever re-adds it to `collapsed`. An opt-IN `expandedKeys`
  // set needs no such catch-up: a key that was never explicitly expanded is
  // collapsed by construction, forever, with no ongoing effect required.
  //
  // The "expand only the most recently active thread" default can only be
  // computed once real thread data has arrived. On a real page load this
  // component mounts (keyed by conversationKey/sceneId, per GameWindow.tsx)
  // the instant sceneId becomes truthy, while useSceneInteractions's
  // useInfiniteQuery is still in flight — so `groups` is empty on that first
  // render. A lazy useState initializer only ever sees that one, empty
  // render and never re-runs once real data lands, so the default silently
  // never applies. Instead: seed synchronously from storage if it exists
  // (and never let the async default fire on top of restored state), else
  // leave `expandedKeys` empty and let the effect below apply the default
  // the first time `groups` is actually populated. `defaultSeeded` guards
  // that effect so it only ever runs once per mount — the user's own
  // subsequent toggles (via toggleThread/bulk expand-collapse) are the only
  // thing allowed to change `expandedKeys` after that.
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(() =>
    storedAnchorState ? new Set(storedAnchorState.expanded) : new Set()
  );
  const defaultSeeded = useRef(storedAnchorState !== null);
  useEffect(() => {
    if (defaultSeeded.current) return;
    if (groups.length === 0) return;
    defaultSeeded.current = true;
    // `mostRecentGroupKey` CAN be null here even though `groups` isn't empty
    // (#3759 Wave 9 fix-round-1 re-review Minor fold-in): it's derived from
    // `realThreadGroups`, which excludes single-pose `legacy:` groups, so a
    // scene made entirely of un-replied narration has no "most recently
    // active thread" to expand -- correctly seeds nothing (legacy poses
    // render plainly regardless of `expandedKeys`, so there's nothing for
    // this default to open). A single-real-thread conversation is trivially
    // its own "most recently active" thread, so this one branch also covers
    // the old `groups.length <= 1` case -- expanded, not collapsed.
    setExpandedKeys(new Set(mostRecentGroupKey ? [mostRecentGroupKey] : []));
  }, [groups, mostRecentGroupKey]);
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
  // #3759 Wave 9 (F1): sorts the FULL `interactions` array, not a windowed
  // slice -- this view is already virtualized via `@tanstack/react-virtual`
  // below specifically so rendering cost doesn't scale with total item
  // count, so it never needed flat windowing on top; capping it there
  // directly contradicted User Story 2 ("switch to Chronological and read
  // EVERYTHING in one continuous timeline"). No per-thread paging UI exists
  // for this view -- the virtualizer already handles arbitrarily long lists.
  const chronologicalItems = useMemo(
    () => [...interactions].sort((a, b) => a.timestamp.localeCompare(b.timestamp) || a.id - b.id),
    [interactions]
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
    expanded?: string[];
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
      expanded: overrides.expanded ?? current?.expanded ?? [],
    });
  };
  // Gate the WRITE only (#3759 review finding I1) -- expanding/collapsing
  // threads stays allowed while reading a reference or a non-room
  // conversation tab (Decision #5 governs the STORED state, not the
  // in-memory `expandedKeys` React state above); it must just never corrupt
  // someone ELSE's stored row. Same two conditions the anchor-save paths
  // below already gate on.
  const persistExpanded = (next: Set<string>) => {
    if (readOnly || !persistAnchor) return;
    persistAnchorState({ expanded: [...next] });
  };
  const toggleThread = (key: string) =>
    setExpandedKeys((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      persistExpanded(next);
      return next;
    });
  const expandAllThreads = () => {
    // realThreadGroups, not groups (#3759 Wave 9 fix-round-1 re-review Minor
    // fold-in): a `legacy:` key is inert in `expandedKeys` (the single-pose
    // branch never reads it), so including it here only persisted noise into
    // localStorage -- a long scene of ordinary narration turned one click
    // into hundreds of stored, meaningless strings.
    const next = new Set(realThreadGroups.map((group) => group.key));
    setExpandedKeys(next);
    persistExpanded(next);
  };
  const collapseAllThreads = () => {
    const next = new Set<string>();
    setExpandedKeys(next);
    persistExpanded(next);
  };
  // #3759 Wave 9 review finding F5: jumps to the most-recently-active thread
  // (reusing `mostRecentGroupKey`, the same computation the default-expand
  // effect above uses), expanding it if needed and scrolling its header into
  // view. Pure UI state + a scroll, like expand/collapse-all -- no mutation,
  // so it needs no `readOnly` gate (unlike "Mark conversation read" below).
  const handleLatestActivity = () => {
    if (!mostRecentGroupKey) return;
    setExpandedKeys((previous) => {
      if (previous.has(mostRecentGroupKey)) return previous;
      const next = new Set(previous);
      next.add(mostRecentGroupKey);
      persistExpanded(next);
      return next;
    });
    const el = rootRef.current?.querySelector<HTMLElement>(
      `[data-thread-id="${mostRecentGroupKey}"]`
    );
    el?.scrollIntoView({ block: 'start' });
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
  // showing. `readOnlyRef`/`interactionsRef`/`expandedKeysRef` mirror the
  // latest render's values for the native (non-JSX) scroll listener below,
  // which is attached once per Threads-view session rather than
  // re-subscribed on every interaction/expand change (re-subscribing would
  // risk dropping an in-flight debounce right when the user is mid-scroll).
  const rootRef = useRef<HTMLDivElement>(null);
  const readOnlyRef = useRef(readOnly);
  readOnlyRef.current = readOnly;
  const persistAnchorRef = useRef(persistAnchor);
  persistAnchorRef.current = persistAnchor;
  const interactionsRef = useRef(interactions);
  interactionsRef.current = interactions;
  const expandedKeysRef = useRef(expandedKeys);
  expandedKeysRef.current = expandedKeys;
  const conversationKeyRef = useRef(conversationKey);
  conversationKeyRef.current = conversationKey;

  // #3759 review finding I2: an anchor older than the default tail window is
  // the COMMON case, not an edge case -- before falling back to scrolling to
  // the bottom, check whether the anchored pose exists ANYWHERE in the full
  // `interactions` array (not just the currently-shown per-thread window)
  // and, if so, widen its OWN thread's window to include it instead of
  // jumping away.
  //
  // #3759 Wave 9 (F1/F2): replaces the old flat `computeWidenTarget`/
  // `widenWindowToInclude` pair (which widened the whole list's single tail
  // window by array position) now that nothing windows the whole list
  // anymore -- only individual threads do. `widenThreadWindow` is the pure
  // core, shared with the deep-link target-seek effect below (#3759 review
  // finding C2): both need "does this thread's OWN window already show
  // everything it has, and if not, expand it to." Per the Wave 9 brief's own
  // recommendation, this widens to the THREAD'S FULL pose count ("show the
  // whole thread") rather than computing a precise partial widen around the
  // target -- simpler and safe because both callers only ever fire on a
  // rare, intentional action (an anchor restore, or a deep-link click), not
  // on every render.
  const anchorRetryPendingRef = useRef(false);
  const widenThreadWindow = (key: string): boolean => {
    const groupLength = interactions.reduce(
      (count, item) => ((item.thread_id || `legacy:${item.id}`) === key ? count + 1 : count),
      0
    );
    const existing = threadWindows[key];
    if (existing && existing.start === 0 && existing.end >= groupLength) return false; // already fully shown
    setThreadWindows((previous) => ({ ...previous, [key]: { start: 0, end: groupLength } }));
    return true;
  };
  // I2's own miss-handling: expands the pose's thread (if collapsed) AND
  // widens its window (if not already fully shown), then flags a retry once
  // both land. Returns false ("not the miss case, don't retry") only when
  // the pose is genuinely absent from `interactions` altogether, OR when its
  // thread is already fully expanded and windowed and the DOM still somehow
  // didn't have it (nothing left to widen -- matches the old
  // `computeWidenTarget`'s identical "already covered" contract).
  const widenThreadWindowToInclude = (poseId: string): boolean => {
    const targetInteraction = interactions.find((item) => String(item.id) === poseId);
    if (!targetInteraction) return false; // genuinely absent from `interactions`
    const key = targetInteraction.thread_id || `legacy:${targetInteraction.id}`;
    let changed = false;
    if (!expandedKeys.has(key)) {
      changed = true;
      setExpandedKeys((previous) => {
        const next = new Set(previous);
        next.add(key);
        return next;
      });
    }
    if (widenThreadWindow(key)) changed = true;
    if (!changed) return false;
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
      // expanded set (e.g. it's inside a collapsed thread, or its thread's
      // own window doesn't reach it, or it's on an older history page not
      // yet fetched). Widen its thread first (I2, above); only fall all the
      // way back to the bottom once the pose is confirmed genuinely absent
      // from `interactions` altogether.
      if (widenThreadWindowToInclude(anchor.poseId)) return;
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
      // #3759 Wave 9 (F1): unlike restoreThreadsAnchor's own miss branch,
      // this has no widen step to try -- `chronologicalItems` (above) is
      // now always the FULL, unwindowed `interactions` array (this view's
      // whole point is a flat, unwindowed timeline; the virtualizer handles
      // its size), so a miss here can ONLY mean the pose is genuinely absent
      // from `interactions` altogether -- the exact same condition
      // `widenThreadWindowToInclude` itself checks first and bails out of.
      // Straight to the bottom-fallback, same reasoning as
      // restoreThreadsAnchor's own fallback above (#3759 review finding I3).
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
  // `widenThreadWindowToInclude` only schedules the wider `threadWindows`
  // entry (and/or the uncollapse); the pose isn't mounted (and thus
  // findable) until the resulting re-render commits, which is exactly when
  // `threadWindows` or `expandedKeys` changes.
  useEffect(() => {
    if (!anchorRetryPendingRef.current) return;
    anchorRetryPendingRef.current = false;
    restoreAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadWindows, expandedKeys]);

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
    if (interactions.length === 0) return;
    restoreSeeded.current = true;
    restoreAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, interactions.length]);

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
  // around the opened pose, but a big thread within that window still only
  // shows its own default per-thread tail (`THREAD_PAGE_SIZE`, #3759 Wave 9
  // F1/F2) -- for a target sitting earlier than that (the common case: a
  // search result or "Recent conversations" row rarely lands in a thread's
  // newest `THREAD_PAGE_SIZE` poses), the default window alone renders
  // everything BUT the pose the user actually opened. Shares
  // `widenThreadWindow` (I2, above) to widen the target's own thread, then
  // scrolls to and briefly highlights the target once its row mounts.
  // `targetSeekDoneRef` (declared above, near `threadWindows` -- see that
  // block's own comment for why) guards this so it runs once per target: a
  // NEW target (switching between reference entries without unmounting,
  // e.g. two search results in the same scene) resets it because the ref
  // stores the id it last completed, not just a boolean; a readOnly
  // transition also resets it (re-opening the same deep link after Return
  // to live must not be a no-op).
  const [highlightedPoseId, setHighlightedPoseId] = useState<string | null>(null);
  useEffect(() => {
    if (!targetPoseId) return;
    if (targetSeekDoneRef.current === targetPoseId) return;
    const targetInteraction = interactions.find((item) => String(item.id) === targetPoseId);
    if (!targetInteraction) return; // not in the loaded window at all -- nothing to seek to
    // Expand the target's own thread (#3759 review Fix round 1 IMPORTANT;
    // updated in Wave 9 fix round 1 finding I-4 for the `collapsed` ->
    // `expandedKeys` model inversion, same behavior): the "expand only the
    // most recently active thread" default (declared earlier, above) would
    // otherwise permanently hide the target's row whenever its thread ISN'T
    // the most recently active one -- the ORDINARY multi-thread case, not an
    // edge case. A functional update composes correctly with whatever the
    // default-expand effect also just enqueued in the SAME commit (declared
    // earlier, so it enqueues first); idempotent and harmless to re-issue on
    // every pass, including once the thread is already expanded.
    // `expandedKeys` is a dependency below specifically so this effect
    // re-runs once that update actually lands.
    const targetGroupKey = targetInteraction.thread_id || `legacy:${targetInteraction.id}`;
    setExpandedKeys((previous) => {
      if (previous.has(targetGroupKey)) return previous;
      const next = new Set(previous);
      next.add(targetGroupKey);
      return next;
    });
    // #3759 Wave 9 (F1/F2): widen the target's own per-thread window too --
    // expanding alone isn't enough for a thread whose default window
    // doesn't reach the target. `threadWindows` is a dependency below so
    // this effect re-runs once the widen actually lands.
    widenThreadWindow(targetGroupKey);
    const targetEl = rootRef.current?.querySelector<HTMLElement>(
      `[data-pose-id="${targetPoseId}"]`
    );
    if (!targetEl) return; // thread not expanded/windowed in the DOM on this pass yet --
    // `expandedKeys`/`threadWindows` changing (once the updates above land) re-triggers this effect.
    targetSeekDoneRef.current = targetPoseId;
    targetEl.scrollIntoView({ block: 'center' });
    setHighlightedPoseId(targetPoseId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetPoseId, interactions, expandedKeys, threadWindows]);

  // Clears the deep-link target highlight ~2s after it's set (#3759 review
  // Fix round 1: the highlight could stick forever when `interactions`
  // changed identity inside the 2s window -- the seek effect above would
  // re-run, its cleanup would clear the pending timeout, but its body would
  // then early-return at the `targetSeekDoneRef` guard without ever setting
  // a NEW one). A separate effect keyed ONLY on `highlightedPoseId` is immune
  // to that churn: it (re)arms a fresh timer whenever a pose is newly
  // highlighted and clears it on unmount or when the highlight changes again.
  useEffect(() => {
    if (!highlightedPoseId) return;
    const timeout = setTimeout(() => setHighlightedPoseId(null), 2000);
    return () => clearTimeout(timeout);
  }, [highlightedPoseId]);

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
          interactionsRef.current.find((item) => String(item.id) === found.poseId)?.thread_id ??
          null;
        persistAnchorState({
          anchor: { poseId: found.poseId, threadId, offsetPx: found.offsetPx },
          expanded: [...expandedKeysRef.current],
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
        interactions.find((item) => String(item.id) === found.poseId)?.thread_id ?? null;
      persistAnchorState({
        anchor: { poseId: found.poseId, threadId, offsetPx: found.offsetPx },
        expanded: [...expandedKeys],
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
      <div className="mx-auto w-full max-w-[var(--play-reading-measure,90ch)] space-y-[var(--play-density-gap,0.75rem)] px-4 py-4">
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            {/* realThreadGroups, not groups (#3759 Wave 9 fix-round-1 re-review
                Minor fold-in): a `legacy:` group is one un-replied pose, not a
                "conversation" -- counting it here visibly contradicted the
                single collapsible card the render actually shows once F1/I-5
                landed. `groups.length` still gates the true-empty fallback,
                since a scene of legacy-only narration should read "0
                conversations", not "New conversation" (it isn't new/empty). */}
            {groups.length
              ? `${realThreadGroups.length} conversation${realThreadGroups.length === 1 ? '' : 's'}`
              : 'New conversation'}
          </span>
          <div className="flex gap-2">
            {realThreadGroups.length > 0 && (
              <>
                <button className="underline" onClick={expandAllThreads}>
                  Expand loaded threads
                </button>
                <button className="underline" onClick={collapseAllThreads}>
                  Collapse loaded threads
                </button>
                {/* #3759 Wave 9 review finding F5. */}
                <button className="underline" onClick={handleLatestActivity}>
                  Latest activity
                </button>
              </>
            )}
            {/* #3759 Wave 9 review finding F6: gated on `!readOnly`, matching the
                existing pattern the per-pose "Reply" button already uses below --
                a live mutating control (a real `POST /api/play/read/`) must not
                survive into a mode Decision #5 calls read-only. Expand/Collapse/
                Latest activity above and the Chronological toggle below are all
                pure UI state, not mutations, so they stay ungated. */}
            {interactions.length > 0 && !readOnly && (
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
                  // #3759 Wave 9 review finding F4: switched from the old
                  // "In a thread"/"Standalone" label to the same
                  // "Opening pose"/"Reply in <title>" phrasing Threads view
                  // uses (see `poseRoleLabel`'s own doc comment). Decided in
                  // favor of consistency: Chronological flattens every
                  // thread into one timeline, so knowing WHICH thread a
                  // reply belongs to (not just that it's "in a thread" at
                  // all) is strictly more useful here, and there's no demo
                  // image for this screen (the review's own scope table
                  // marks it `textonly`) to visually contradict.
                  const groupKey = item.thread_id || `legacy:${item.id}`;
                  const roleLabel = poseRoleLabel(item, groupByKey.get(groupKey)?.interactions[0]);
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
                        {roleLabel && <p className="text-xs text-muted-foreground">{roleLabel}</p>}
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
                            interactionsById={interactionsById}
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
              // #3759 Wave 9 fix round 1 finding I-5: `thread_id` is only
              // set for an interaction that's an EXPLICIT reply
              // (`interaction_services.py`) -- ordinary, un-replied room
              // narration is the COMMON case and gets `thread_id=null`,
              // keyed `legacy:${id}` here (see `groups`'s own grouping key
              // above). Since that key is unique per interaction id, a
              // `legacy:`-keyed group can never hold more than its one
              // pose -- checking the key prefix is equivalent to "this
              // pose was never replied to" and doesn't need a separate
              // length check. F1 makes every group always visible, so
              // without this branch, EVERY ordinary un-replied pose in a
              // scene would render as its own always-visible collapsible
              // "thread" card (header, chevron, collapse toggle) -- a real
              // scene of ordinary room chatter would be a wall of
              // one-pose accordions. A group with a real, explicit
              // `thread_id` (even one with only a single reply so far --
              // more could still arrive) keeps the full card treatment
              // below, unchanged.
              //
              // Deviation from the fix-round brief's literal wording (noted
              // in the wave report): the brief describes this as "the same
              // visual form Chronological view already gives a single
              // pose," which has NO "Show less"/"Reply" footer at all. That
              // exact substitution regressed a real, tested integration
              // (`GamePage.test.tsx`'s reference-mode round-trip test): its
              // fixture pose has no `thread_id` either -- the single most
              // common shape a scene starts in -- and replying to a
              // standalone pose is literally how a NEW thread begins.
              // Keeping the per-pose fold/Reply footer (identical to a real
              // thread's own per-pose footer, just below) doesn't
              // reintroduce anything THREAD-level (no header/chevron/
              // collapse toggle survives), so it still satisfies the
              // brief's own explicit, unambiguous requirement.
              if (group.key.startsWith('legacy:')) {
                const item = root;
                const poseCollapsed = collapsedPoses.has(item.id);
                return (
                  <div key={group.key} data-thread-id={group.key}>
                    <PoseReadTarget
                      pose={{ id: item.id, timestamp: item.timestamp }}
                      observe={observe}
                      highlighted={String(item.id) === highlightedPoseId}
                    >
                      {/* #3759 Wave 9 review Minor M-1: `poseRoleLabel` itself
                          returns "Standalone" here (gated on `item.thread_id`,
                          not merely "is this the group's root"), never
                          "Opening pose" -- that label asserts a thread that
                          doesn't exist for a genuinely un-replied pose. */}
                      <p className="text-xs text-muted-foreground">{poseRoleLabel(item, root)}</p>
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
                          {/* #3787 D1: the involved viewer reads the row ONCE,
                              inside the marked treatment, instead of reading the
                              plain bubble and then a restatement of the same
                              sentence. `poseBody` is the identical per-viewer
                              rendering either way. */}
                          {(() => {
                            const poseBody = (
                              <SceneMessages
                                sceneId={sceneId}
                                filteredInteractions={[item]}
                                onAvatarClick={onAvatarClick}
                                onAddTarget={onAddTarget}
                                onAttachAction={onAttachAction}
                                readOnly={readOnly}
                                interactionsById={interactionsById}
                              />
                            );
                            if (!isInvolvingViewer(item, viewerPersonaId) || !onReply) {
                              return poseBody;
                            }
                            return (
                              <InvolvementFlag
                                item={item}
                                onReply={onReply}
                                readOnly={readOnly}
                                venue={viewerVenue}
                              >
                                {poseBody}
                              </InvolvementFlag>
                            );
                          })()}
                          <div className="flex items-center justify-end gap-2 px-2 text-xs text-muted-foreground">
                            <button
                              type="button"
                              className="inline-flex min-h-9 items-center gap-1 underline"
                              onClick={() => togglePose(item.id)}
                            >
                              Show less
                            </button>
                            {onReply && !readOnly && !isInvolvingViewer(item, viewerPersonaId) && (
                              <ReplyControl
                                item={item}
                                onReply={onReply}
                                involved={false}
                                venue={viewerVenue}
                              />
                            )}
                          </div>
                        </>
                      )}
                    </PoseReadTarget>
                  </div>
                );
              }
              const isCollapsed = !expandedKeys.has(group.key);
              const unread = group.interactions.filter(isEffectivelyUnread).length;
              // #3759 Wave 9 (F1/F2): per-thread pose window, replacing the
              // old flat whole-list tail-slice. `end < group.interactions.length`
              // ("more poses hidden after what's shown") is only ever true
              // once THIS thread has an explicit `threadWindows` entry whose
              // `end` has fallen behind the thread's current length -- e.g.
              // new poses arrived in this thread after the user had already
              // paged earlier into its history. The untouched default
              // (`resolveThreadWindow`'s no-entry branch) always recomputes
              // `end` from the CURRENT length, so it never falls behind.
              const { start, end } = resolveThreadWindow(group);
              const clampedStart = Math.min(start, end);
              const visiblePoses = isCollapsed ? [] : group.interactions.slice(clampedStart, end);
              const hiddenEarlierCount = clampedStart;
              const hiddenLaterCount = Math.max(0, group.interactions.length - end);
              return (
                <section
                  key={group.key}
                  className="overflow-hidden rounded-lg border bg-card/60"
                  data-thread-id={group.key}
                >
                  <button
                    type="button"
                    className="flex min-h-11 w-full items-start gap-2 px-3 py-2 text-left hover:bg-accent/40"
                    aria-expanded={!isCollapsed}
                    aria-controls={`thread-${group.key}`}
                    onClick={() => toggleThread(group.key)}
                  >
                    {isCollapsed ? (
                      <ChevronRight className="mt-0.5 h-4 w-4 shrink-0" />
                    ) : (
                      <ChevronDown className="mt-0.5 h-4 w-4 shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
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
                      </div>
                      {/* #3759 Wave 9 review finding F3: opening-pose excerpt +
                          timestamp (reuses PoseUnit.tsx's own `toLocaleString()`
                          convention for consistency with every per-pose
                          timestamp elsewhere in the reader). */}
                      {root && (
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                          {excerptOf(root.content)} · {new Date(root.timestamp).toLocaleString()}
                        </p>
                      )}
                    </div>
                  </button>
                  {!isCollapsed && (
                    <div id={`thread-${group.key}`} className="border-t px-2 py-2">
                      {hiddenEarlierCount > 0 && (
                        <button
                          type="button"
                          className="mb-2 w-full rounded border px-3 py-2 text-sm"
                          onClick={() =>
                            setThreadWindows((previous) => ({
                              ...previous,
                              [group.key]: {
                                start: Math.max(0, clampedStart - THREAD_PAGE_SIZE),
                                end,
                              },
                            }))
                          }
                        >
                          Load earlier replies · {hiddenEarlierCount} before this page
                        </button>
                      )}
                      {visiblePoses.map((item) => {
                        const poseCollapsed = collapsedPoses.has(item.id);
                        const roleLabel = poseRoleLabel(item, root);
                        return (
                          <PoseReadTarget
                            key={`pose-${item.id}`}
                            pose={{ id: item.id, timestamp: item.timestamp }}
                            observe={observe}
                            highlighted={String(item.id) === highlightedPoseId}
                          >
                            {/* #3759 Wave 9 review finding F4. */}
                            {roleLabel && (
                              <p className="text-xs text-muted-foreground">{roleLabel}</p>
                            )}
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
                                {/* #3787 D1 -- see the Chronological branch. */}
                                {(() => {
                                  const poseBody = (
                                    <SceneMessages
                                      sceneId={sceneId}
                                      filteredInteractions={[item]}
                                      onAvatarClick={onAvatarClick}
                                      onAddTarget={onAddTarget}
                                      onAttachAction={onAttachAction}
                                      readOnly={readOnly}
                                      interactionsById={interactionsById}
                                    />
                                  );
                                  if (!isInvolvingViewer(item, viewerPersonaId) || !onReply) {
                                    return poseBody;
                                  }
                                  return (
                                    <InvolvementFlag
                                      item={item}
                                      onReply={onReply}
                                      readOnly={readOnly}
                                      venue={viewerVenue}
                                    >
                                      {poseBody}
                                    </InvolvementFlag>
                                  );
                                })()}
                                <div className="flex items-center justify-end gap-2 px-2 text-xs text-muted-foreground">
                                  <button
                                    type="button"
                                    className="inline-flex min-h-9 items-center gap-1 underline"
                                    onClick={() => togglePose(item.id)}
                                  >
                                    Show less
                                  </button>
                                  {onReply &&
                                    !readOnly &&
                                    !isInvolvingViewer(item, viewerPersonaId) && (
                                      <ReplyControl
                                        item={item}
                                        onReply={onReply}
                                        involved={false}
                                        venue={viewerVenue}
                                      />
                                    )}
                                </div>
                              </>
                            )}
                          </PoseReadTarget>
                        );
                      })}
                      {hiddenLaterCount > 0 && (
                        <button
                          type="button"
                          className="mt-2 w-full rounded border px-3 py-2 text-sm"
                          onClick={() =>
                            setThreadWindows((previous) => ({
                              ...previous,
                              [group.key]: {
                                start: clampedStart,
                                end: Math.min(group.interactions.length, end + THREAD_PAGE_SIZE),
                              },
                            }))
                          }
                        >
                          Load later replies
                        </button>
                      )}
                    </div>
                  )}
                </section>
              );
            })
          ))}
        {/* #3759 Wave 9 (F1/F2): this is now the ONLY remaining whole-list
            control -- fetching MORE data from the server (a different
            concern than deciding how much of already-fetched data to
            render, which per-thread windowing above now owns entirely).
            No more local "Jump to latest": since every thread is always
            visible and each has its own window, there's no longer a single
            local window to jump back from. */}
        {hasNextPage && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={fetchNextPage}
              className="flex-1 rounded border px-3 py-2 text-sm"
            >
              Load earlier history
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
