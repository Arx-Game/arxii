# Arx II narrative play: implementation specification

Status: design for issue #3731. This document replaces the preliminary layout guidance in the initial design snapshot. It authorizes no implementation, deployment, or change to scene-retention policy. The requested next phase is implementation by a separate agent.

## 1. Outcome and scope

The browser play surface at `/game` is a narrative reader and writer with one contextual sidebar. It never becomes a terminal. Players can enter the world, understand a room, inspect its occupants and objects, move, write poses, follow and collapse exchanges, consult earlier conversations, inspect their character, and handle scene/combat actions without knowing command syntax.

Long-form RP is the design baseline: hundreds of interactions, routinely several paragraphs each. Threading, historical reference, independent scrolling and safe draft handling are required for the first complete release, not optional archival polish.

Keep the current live-session architecture on `/game`. Scene record pages remain direct-link destinations, but following a reference from play must work within the play workspace. Existing rules, permission checks, action dispatch, flows and triggers remain authoritative. No mockup content or example action becomes a hardcoded game mechanic.

### Requirements from the user

1. Remove all player-facing terminal states.
2. Use one sidebar, with more width for the main reader and composer. Either sidebar side is acceptable.
3. Main history and sidebar scroll independently, each with an accessible scrollbar.
4. Support hundreds of multi-paragraph poses, with smaller adjustable typography.
5. Make interactions threaded and collapsible.
6. Make earlier scenes, whispers and other accessible communications manageable to find and consult.
7. Accommodate OOC channels and future interface customization; do not delay terminal removal for a full layout editor.
8. Character-entry protocol hardening is secondary to the presentation work.

### Working defaults selected for a concrete implementation

Confirmed reference behavior: historical scenes and whispers open in the same wide reader, preserve the live draft, and provide a clear return to live.

The remaining concrete design defaults are: sidebar on the right; explicit reply relationships within audience-specific conversations; shallow thread presentation; 14px desktop prose; a compact default; per-account, per-browser preferences. These are proposed defaults rather than claims of separate user ratification. Explicit reply semantics remain open to later clarification; use the specified model unless the user changes it.

Out of scope for this release: arbitrary floating windows, drag-and-drop dashboard construction, AI-written summaries, manual merging/splitting/reparenting of other people's threads, cross-scene reply chains, changing record-retention policy, offline posting, a new combat rules engine, or creating a second OOC channel backend.

## 2. Vocabulary and information architecture

| Term | Meaning |
| --- | --- |
| Pose | Player-facing name for an IC contribution. Preserve the repository's vocabulary; `Interaction` is the backend entity. |
| Conversation | An audience and delivery context: a room/scene, a place gathering, a fixed whisper participant set, or an OOC channel. Selection determines which feed is read; delivery is separately validated. |
| Thread | A root pose and explicit responses to it inside one conversation/context. Thread membership organizes reading; it grants no permissions. |
| Reply | A new pose with a specific parent reference. It stays in its parent's thread, with a visible “Replying to …” context. |
| Reference mode | Read-only viewing of historical material in the main reader while live presence and the live draft remain intact. |
| Inspector | The selected person/object/character/action detail displayed within the single sidebar. |
| Live context | The active character/persona, room, scene, audience and server-confirmed ability to send. It is distinct from the reference currently being read. |

Do not equate an IC target with a private receiver. Existing target-based filtering remains available, but a target chip does not create privacy. Distinguish scene-local OOC, persistent public/org OOC channels, private whispers, player mail and IC missives in labels and navigation.

## 3. Layout, typography and scrolling

### Desktop default

- One compact app header, 56px minimum, with Arx, World, Scene, History, active character/persona and display settings. Preserve access to wider account/site navigation through the app menu. Do not stack the full marketing header over a second game header.
- A flexible main column and a 280px right sidebar, separated by a resize handle/border. Sidebar adjustable from 240–360px; clamp so the main column remains at least 600px where possible. Left placement is a preference using the same content and state.
- At widths below 960 CSS px, use a single visible pane with explicit Story / Sidebar controls. Maintain both pane states; switching does not unmount the composer or discard drafts. At 200% zoom the narrow layout is expected.
- Main column: compact location/scene heading, conversation/thread toolbar, scrollable reader, optional action-required strip, persistent composer. Only the reader consumes its flexible scrolling region.
- Sidebar: compact mode controls followed by one scroll container. Its sections share that scroll container. Do not give each list/card its own scrolling box. Drawers/dialogs can scroll when their content genuinely requires it; they are temporary tools, not additional persistent panes.
- Constrain the page to available app height using flex/grid with `min-height: 0`; preserve safe-area and mobile visual-viewport behavior. The main page should not become a third scrolling transcript. Test mobile keyboard opening and closing.
- Reader and sidebar use native scrolling with stable scrollbar gutters. Scrollbars must remain discoverable and keyboard-operable; honor OS autohide preferences instead of emulating a custom scrolling mechanism.
- Prose and the composer share an approximately 90ch maximum content measure within the wide main column. Leave optional extra space as margins at very large widths. The width preference can range from 72–110ch; never shrink the main column solely to fit decorative panels.

### Type and density defaults

| Setting | Default | Supported first-release choices |
| --- | --- | --- |
| Desktop prose | 14px, system sans-serif, 1.55 line height | 12–20px in 1px steps; sans-serif or serif |
| Phone prose | 16px | Same user-selected range; editable fields remain at least 16px to avoid focus zoom |
| Scene title | 24px desktop / 22px phone, serif | No oversized hero title during active RP |
| Metadata | 12px | Never below 11px; author/audience remain legible |
| Density | Compact: 12px between poses, 8px between paragraphs, 12px card padding | Comfortable: 20px / 12px / 16px |
| Thread indentation | One 12px level maximum | Deeper replies use a parent-reference chip, not further indentation |
| Composer | Initially 5 lines, grows to 35% of available pane height | User resize; internal editor scrolling after the cap |

Use the existing theme system and design tokens; the dark green-gray / warm paper and restrained gold treatments in the concept are the visual direction. Use shadcn/Radix components already available. Images are optional: a room with no art must still look complete. During active scenes no decorative hero image may push the reader off screen.

Scroll behavior is a contract: sidebar inspection cannot change the main reader position; new poses cannot move a reader inspecting earlier content; font changes and expansion must restore the same visible interaction and approximate intra-pose text position. Store anchors by stable interaction/thread identity with an offset, never only a raw global scrollTop. After deletion, fall back to the nearest still-visible neighbor.

## 4. What lives in the sidebar

The sidebar has three modes: **Here**, **Conversations**, **History**. Each owns a remembered scroll position within the same sidebar scroll container. A detail view temporarily replaces the mode content with a Back control; it does not create another permanent pane.

**Here** defaults to: room description (compact summary with Show more), observable occupants, places/objects, available exits, character condition and a Character sheet action. Clicking a person/object opens its inspector in the same sidebar. Reuse the existing focus stack. Keep high-priority actionable scene prompts in the main column even while a different sidebar mode is selected.

**Conversations** groups: current room/scene, current place gatherings, whispers, scene-local OOC, subscribed OOC channels. Separate headings and audience indicators are essential. Public/org OOC channel availability, identity and notification policy come from #3299. If that backend is not delivered yet, omit unavailable channel rows; do not ship fake channels or route to Evennia Public as a fallback. Scope and label this dependency explicitly in the release notes.

**History** contains a search field, type selector (All accessible / Scenes / Whispers / OOC), optional participant/date filters, and results grouped by conversation. Default to this character's relevant recent conversations; offer an explicit All my accessible history scope without switching the active character. Do not show every public scene in the default recent list. Results include authorized scene/conversation title, time, visible participants and an authorized short excerpt. Search opens references in the main reader. Load more results within the sidebar's shared scroll container.

The current location, active persona and composer audience stay visible even while History or an inspector replaces Here. An urgent prompt is always reachable via a compact count/action beside the composer. Encounter decisions use the Here inspector; opening them does not navigate away from the reader.

## 5. Thread behavior

### Creation and audience

- A normal pose with no reply selected starts a root. Reply selects a parent pose and creates a response in the same thread. The composer shows the parent author and a short authorized excerpt, with a clear Cancel reply control.
- Thread replies stay within the same scene/room-context and audience kind. Closed/historical scene replies are disabled. Referencing an old scene does not reopen it or attach a live pose to its old thread.
- For fixed private groups, changing the recipient set starts a new conversation/thread. Server checks actual eligible recipients again on send. Never silently replace a missing recipient with a public audience.
- For room-wide conversation, current authorized room participants remain governed by existing delivery rules. A thread does not expose earlier restricted poses to newly arrived readers. Validate writer access to the parent; render parent context only if the current viewer can read it.
- Public-target grouping can narrow a view but does not substitute for explicit reply identity. Cross-audience reference/quotation is not supported in this release; the user can write new prose, but the client must not automatically copy private text into a public draft.
- Existing legacy poses without reply metadata remain standalone roots. Do not infer historical reply relationships from proximity, names, timestamps or text.

### Presentation and order

Default reader view is **Threads**. Roots are ordered by creation time, oldest to newest within a loaded range. Replies within a thread are chronological and shallow; a parent chip supplies the relationship. A new reply updates its existing thread in place, never reorders all roots by latest activity while someone is reading.

Offer **Chronological** as a reading preference: all accessible poses ordered by time, each linked to its thread/parent. Switching preserves a separate anchor for each mode. Whole-thread collapse preferences belong to Threads view; Chronological retains individual-pose collapse without secretly removing later replies. The two views share content and read state.

On first opening a populated conversation, load the latest 20 thread summaries and expand the most recently active thread, fetching a page around its first unread pose (or its latest poses when there are no unread poses). Other threads have an explicit collapsed summary. This is visible grouping, not silent truncation. Provide Expand loaded threads / Collapse loaded threads; these operate only on loaded groups and do not trigger an unbounded history fetch. An empty conversation has a purposeful invitation to begin.

Existing interactions without explicit parents appear as independent roots in their authorized audience/context; never infer replies from proximity or matching names. Chronological view gives existing long scenes a continuous reading path. New unparented poses start new threads. The composer offers an explicit Cancel reply control, returning to a new thread without deleting the draft text. Reply-to-parent navigation uses the same temporary reveal behavior as a history target.

Collapsed summary: root author/authorized opening excerpt, visible participant names or count, visible reply count, latest visible activity, unread count and direct-attention marker. It remains usable even when the root was deleted/blocked or is inaccessible: label the group from its first accessible contribution or use “Conversation”; never reveal an inaccessible root's name/excerpt/count. No AI summary.

An expanded thread shows a root and one page of replies, with explicit Load earlier/later replies controls where needed. Individual long poses have Show less / Show full pose; default is full text within an expanded thread. For collapsed poses show the author and first three visible lines with an explicit expansion control. Store these choices per viewer/conversation/thread/pose.

New replies do not force collapsed threads open. A collapsed thread's unread badge changes; an action-needed notice is also exposed beside the composer. A “New activity in N threads” control visits the first unread visible contribution in each affected thread in order. Jump to latest means latest visible activity, not blindly the bottom-most root.

Search and reference links temporarily reveal the required thread/pose and highlight the match. They do not overwrite unrelated collapse preferences. Returning restores the previous live view, anchor and expansion choices. An inaccessible/deleted target shows “This pose is no longer available” with a safe route back; no author/content metadata is exposed by the failure.

## 6. Reading and returning to history

Main reader has two modes: live and reference. Switching is display navigation, never movement, joining a scene, puppeting a character, or a change of composer recipients.

In reference mode show a persistent strip: “Reading history · [authorized conversation title/date]” and **Return to live · N new**. The live composer is replaced visually by a compact “Draft preserved for [live destination]” tray; its underlying draft remains intact. The historical reader is read-only. Return to live restores the prior live reader anchor (not automatically latest); Jump to latest is a separate action.

Opening another historical reference pushes a reference-only navigation entry. Browser Back restores the preceding reference or live view without leaving `/game` unnecessarily. Store reference identifiers in URL query parameters so reload/direct links resolve, subject to authorization; do not put draft text, hidden identities or excerpts in URLs. Copy link copies an internal pose reference, not its body. Copying visible prose remains a normal selection/copy action.

Earlier scenes use their true scene context. Whisper histories group by the exact participants shown at the time, with scene/time separators; grouping across scenes grants no cross-scene delivery ability. Changing masks must not silently identify them as the same person. Public/room history must not reveal private exchanges through reply counts, search results, excerpts or grouped participants.

### Retention and scope

Keep existing PUBLIC, PRIVATE and EPHEMERAL behavior and explicit scene-record agency. Normal retained interactions can be found while authorized. EPHEMERAL text is never placed in persistent caches, drafts of received content, a search index or new durable thread-body storage. The UI labels it “Temporary · not saved”; after reload/restart it must not imply that omitted text can be recovered. Ephemeral author drafts remain memory-only.

Current `visible_to` applies a default 90-day query bound. That is a query default, not proof of deletion. The history UI defaults to the last 90 days but offers an explicit Earlier date range and uses that range for queries. Opening a known retained scene/pose uses the relevant timestamp range rather than silently excluding it due to the default. Do not invent permanent retention or a new deletion schedule in this feature.

For live ephemeral scenes, retain all received content in memory for the active page session up to a documented operational limit (initial target: 2,000 poses or 20 MiB of text per active conversation, whichever first). Warn before eviction with “Older temporary poses will leave this device's view”; do not claim server backfill exists. Clear ephemeral buffers when the page session ends or the server revokes access. Reconnection reports any unrecoverable gap. This limit is an explicit constraint to validate, not a replacement for normal paginated retained history.

## 7. Unread and attention

Read is a property of a visible pose, not merely opening a conversation tab or expanding its parent. Mark a pose read only while the app is foreground and its rendered body is visible for at least one second. Tall poses count once the reader has visited their final visible text block; provide Mark conversation read for intentional bulk dismissal. Collapsed summaries alone do not mark hidden bodies read. The user's own sent poses do not count as unread.

Maintain direct attention (whispers, explicit IC targets/replies addressed to this persona, requests needing an answer) separately from ambient new activity. Channel notifications obey #3299 preferences. Do not produce a sound/toast for every ambient pose by default. Read-state changes are private to the reader, not delivery/read receipts shown to other players.

Use per-interaction seen IDs or sparse seen ranges with gaps; a single maximum ID cannot correctly represent skipped/collapsed content. In particular, existing negative ephemeral IDs must never be compared as chronological high-water marks. IDs are identity, timestamps plus a stable tie-breaker define order. Aggregate counts only over authorized interactions and the applicable unread baseline. On first opening old historical material it is not all newly unread; baseline is established when the viewer follows/subscribes to a live conversation.

## 8. Composer and actions

Always display speaking persona, mode, audience and thread/reply destination. Enter inserts a newline. Ctrl/Cmd+Enter submits (respect IME composition); the visible Send button always works. Do not use plain Enter-to-send by default. Preserve paragraph structure, current formatting features, language choices, persona/guise/companion attribution and action attachments where applicable. Reuse safe rich-text rendering; never inject untrusted HTML.

Keep the existing 10,000-character pose maximum unless separately changed by the domain. Show a character count near the limit and a field error over it; never silently clip text. Model the draft as content plus persona, mode, language, recipients, reply reference, scene/room-context and attachments. Scope it by authenticated account, current tenure/character, conversation/context and audience. A reply target is part of that draft, not a global transient flag.

When changing to another live conversation, save the current draft and restore the destination's draft. When changing identity, room, scene, recipient set or companion, revalidate attachments and show unavailable targets without deleting prose. A stale draft for the previous location is recoverable through Drafts but is never automatically sent into the new room. Travel does not copy the draft to the new context.

Persist the author's unsent normal drafts in per-tab session storage (debounced 500ms), scoped by account and stable IDs; remove on successful acknowledgement or explicit discard. No received RP content is stored there. Private drafts stay per-tab and are cleared on logout/account change; ephemeral drafts are memory-only. Handle unavailable/quota-full storage with a small “Draft kept in this tab only” notice. Closing a tab with unsent content uses the browser's standard unsaved-changes guard. Browser-crash/cross-device draft recovery is not promised in this release.

Submit states: editing → submitting → acknowledged, rejected, or outcome unknown. Keep the submitted content until acknowledgement and never clear a newer edited draft when an older request finishes. A response and its websocket echo merge into one pose. Send attempts carry a client request ID; retries of the same content/context reuse it. A content change is a new request ID. The server must make accepted submissions idempotent by account/request ID and reject reuse with a different payload. Unknown outcome shows Check status / Retry, not an automatic duplicate send.

Action selection consumes the existing available-actions endpoint and existing server target/cost/risk metadata. Intent/action validation uses `dispatch_player_action` / existing registered actions. Preserve the before-action intent event. An attached mechanical action has its own acknowledged identity and is not executed again when retrying prose. Do not silently execute an action before its intended prose without an explicit presentation of the separate outcome.

Existing non-pose socket command paths clear drafts immediately after sending text. They must gain a structured acknowledgement adapter before they can claim the above contract. Using the existing command implementation behind an internal adapter is acceptable during migration; exposing command syntax/raw terminal output to the player is not. Extending the character-entry protocol itself can be a separate delivery slice.

## 9. Lifecycle and feedback states

| State | Main surface | Composer/actions |
| --- | --- | --- |
| Account unauthenticated | Normal sign-in route | No game composer |
| Account ready, no character entered | Character entry card / roster action | No raw account help |
| Entering | Character + last known location, progress and retryable failure | Disabled until confirmed actor/room snapshot |
| Ready, no scene | Room exploration plus structured ambient poses | Authorized room actions available |
| Ready, active scene | Thread reader and scene context | Normal composer |
| Encounter active | Same reader; encounter decision in sidebar, action-needed strip in main | Draft preserved; server-enforced action availability |
| Reference mode | Historical reader with Return to live | Live draft tray, no historical send |
| Reconnecting/stale | Existing content labeled stale; concise reconnect status | Disable authoritative sends; preserve editing draft |
| Error | Contextual error and retry where recoverable | Preserve entered data and known outcomes |
| Finished encounter/scene | Readable aftermath/record status; return to exploration as appropriate | Revalidate context, retain stranded draft |

Socket open is not character entry success. Confirm readiness from an actor/room snapshot associated with the requested stable character ID. Ignore stale responses from an earlier connection generation or another character. On reconnect, reauthorize current context, reconcile pending submissions, then backfill retained history before showing Ready. Unknown presence must not activate the composer.

Route typed data to its owning view: room state → surroundings, interactions → reader, action result → attached action/contextual notice, consent/hazard prompt → action-needed strip, channel push → channel adapter, mail/missive arrival → corresponding navigation notification, lifecycle changes → session state. Never infer authoritative room state by parsing ANSI text. Strip terminal formatting from any legacy player-facing notice adapter and distinguish useful game feedback from login/debug output. Unknown protocol frames go to developer diagnostics; show a concise connection/support notice when they block play. Do not silently discard a required player decision because its new widget is unavailable.

## 10. Data contracts and backend work

This section specifies behavior and minimum fields. Add to existing endpoints/types where compatible rather than duplicating the action/scene systems. Names below are proposed contract names; keep them consistent across generated API types, tests and implementation.

### Read boundary

All conversation lists, thread summaries, poses, search results, surrounding-context requests and read counts use the canonical `InteractionQuerySet.visible_to` policy, block/mute rules, viewer-resolved persona presentation and language comprehension. Search must match text as visible/comprehensible to this viewer; a database match on concealed/garbled raw text must not reveal a secret through a hit or snippet. Do not expose a hidden actor/recipient through a title or filter suggestion.

Existing detail permissions and list visibility use different tests in places (current persona versus pinned writer/receiver account). Resolve that inconsistency for the new read boundary: private-history party access follows the documented pinned-account rule, not character inheritance. A new holder of a persona does not inherit a prior player's whispers. A formerly participating account retains only access permitted by the canonical policy. GM/staff and VERY_PRIVATE behavior remain as documented. Test list/detail/search consistency before enabling history links.

### Core read shapes

```ts
type PoseRef = { id: string; timestamp: string }; // opaque string IDs, including transient IDs
type ReadAnchor = { pose?: PoseRef; threadId?: string; offsetPx: number };
type ConversationKind = 'room' | 'place' | 'whisper' | 'scene_ooc' | 'channel';
type ConversationRef = { kind: ConversationKind; key: string };
type Availability = 'retained' | 'temporary' | 'unavailable';
type Page<T> = {
  results: T[];
  before: string | null;
  after: string | null;
  snapshot: string;
};
type ConversationSummary = {
  ref: ConversationRef;
  title: string;                 // authorized display only
  availability: Availability;
  canRead: boolean;
  canSend: boolean;
  sceneId: string | null;
  latestVisiblePose: PoseRef | null;
  unread: number;
  directUnread: number;
};
type ThreadSummary = {
  id: string;
  conversation: ConversationRef;
  root: PoseRef | null;           // null if unavailable to this viewer
  firstVisible: PoseRef;
  latestVisible: PoseRef;
  opening: string;               // viewer-rendered text, never a raw hidden root
  visiblePoseCount: number;
  unread: number;
  directUnread: number;
};
// Extend the existing Interaction DTO rather than recreating its action/reaction fields:
type ThreadFields = {
  threadId: string;
  replyTo: PoseRef | null;        // only disclose a readable parent
  conversation: ConversationRef;
  availability: Availability;
  clientRequestId?: string;      // writer's acknowledgement only
};
```

Opaque cursors bind the filter, context, viewer and deterministic `(timestamp,id)` ordering. A page is returned in ascending reading order even when fetching the latest window. The snapshot prevents arrivals from shifting an older page boundary. For thread-group pages root order is stable creation order; latest-visible activity is separate metadata.

Minimum operations:

| Operation | Contract |
| --- | --- |
| `GET /api/play/conversations/` | Paginated authorized navigator summaries; kind, character scope, dates and query filters. Default 30 summaries. |
| `GET /api/play/threads/` | Conversation + optional before/after cursor; 20 summaries/page. No unauthorized root/count metadata. |
| `GET /api/play/poses/` | Conversation, optional thread, before/after cursor; 50 poses/page, capped at 100. Reuse existing serialization/enrichment. |
| `GET /api/play/context/` | Authorized PoseRef + conversation; up to 25 earlier and 25 later visible poses, thread identity and surrounding cursors. Unauthorized and missing references have the same non-leaking unavailable response. |
| `GET /api/play/search/` | Query length 2–200, scope/type/person/date filters; 30 results/page, matching only authorized viewer-visible content. Default 90 days, explicit older range supported. Return PoseRef, conversation and visible excerpt. |
| `POST /api/play/read/` | Up to 100 authorized persisted PoseRefs per batch, idempotent; update only private reader state. Separate explicit mark-all-before-snapshot operation for deliberate dismissal. |
| `GET /api/play/submissions/{clientRequestId}/` | Authenticated writer only: pending, acknowledged (pose/action references), rejected (typed reason), or unknown. No lookup of another writer's requests. Unknown is not proof that nothing was sent. |
| Existing write boundary + extension | Accept parent reference, client request ID and expected actor/scene/room context; return acknowledged pose identity or typed rejection. Preserve all existing pose/action fields and validation. |

Read endpoint paths are additive so existing `/api/interactions/` consumers need not change atomically. Internally share visibility/query/serialization behavior; avoid parallel implementations of privacy. Search/filter handling belongs in FilterSets as repository conventions require. Allow a small set of supported sort/filter shapes, not arbitrary query construction.

Typed write failures distinguish validation (field errors), stale context (refresh required), denied audience/action (no fallback destination), request-ID payload conflict, rate limiting (retry delay), and unresolved transport outcome. Authorization failures preserve the draft but disable sending until resolved. Retryable reads preserve existing content. Request acknowledgement metadata must contain only the payload digest and permitted outcome references needed for deduplication, not a second stored copy of private or ephemeral text. Define and test the server's deduplication lifetime; once an old request cannot be reconciled, require explicit review before creating a new submission rather than presenting retry as guaranteed duplicate-free.

### Metadata and persistence

Use existing `Interaction` bodies and receiver records as the source of truth. Introduce thread/reply metadata without duplicating pose content. A concrete suitable shape is `InteractionThread` (UUID, context identity, creation time) and `InteractionThreadMember` (thread FK, unique interaction reference, interaction timestamp, optional parent reference/timestamp). Root is the first member; replies reference existing members. Membership is immutable after successful send in this release. Creation and membership assignment are atomic and retries do not create extra roots.

Context captures scene ID when present and the room profile ID at the time of scene-less creation; it must not be inferred from where a character is standing today. Use the existing RoomProfile/domain model, not a new raw ObjectDB dependency. Legacy scene-less rows without recoverable location remain in authorized general history with “Location unavailable”; never guess a past room.

Validate: parent exists and is readable by the writer; same live context and allowed audience; parent is older than child; no cycles; an unavailable/deleted parent cannot be used for a new reply. After an already-linked parent is removed, retain the remaining permitted thread with generic unavailable context. Public/private filters apply independently to every member. In private fixed-participant conversations normalize the participant set and enforce it server-side; never trust a client-supplied thread key as proof of membership.

**Partition trap:** Interaction is a monthly partitioned table with composite database PK `(id,timestamp)` and existing bridges use `db_constraint=False` plus explicit integrity handling. Do not add an ordinary single-column database FK to its ID. Follow the established timestamp-aware bridge/migration pattern; keep Django migration state and partition SQL/drift checks consistent. Add indexes for conversation/root pagination and parent/member lookup. Validate in Postgres CI even where local SQLite tests are possible.

Read state can use an `InteractionReadReceipt` keyed by authenticated account and stable pose reference, with timestamps; batches are idempotent. Equivalent sparse intervals are acceptable only if tests prove that collapsed gaps remain unread. Do not show read receipts to authors. Ephemeral threading/seen state stays in live memory, with opaque stable event/thread IDs and no persisted body or topology that reconstitutes private text.

For ephemeral replies, the authoritative live session tracks only the active thread/member identities and audience needed to validate a parent. A reconnect may restore metadata only while that live state still exists; it must not imply body replay. If the parent can no longer be validated, reject the reply reference, preserve the author's draft, and offer an explicit new-thread action. Never persist ephemeral Interaction rows merely to obtain a parent ID.

Layout preferences and collapse/anchor metadata are distinct from content. Account-and-browser scoped local storage, schema version 1, holds sidebar side/width, prose settings, density, reader mode and up to 100 recently viewed conversation anchors/collapse states (LRU). Clear account-specific metadata on logout/account change; handle corrupt/unsupported versions by using defaults. Keep IDs opaque and never persist displayed private names or excerpts in navigation metadata. Normal drafts use session storage as section 8 specifies. Server-validated read state survives devices; browser layout/drafts do not promise cross-device synchronization.

## 11. Rendering, performance and access

Do not ship the current `MAX_WS_INTERACTIONS = 200` truncation as a history policy. Retained data can be evicted from a bounded client cache only when recoverable by cursor/reference; store anchors independently. Ephemeral handling follows its explicit separate limit.

Use variable-height windowing for large rendered histories with stable keys and measured heights. No virtual-list package is currently declared in the inspected frontend package manifest; choosing/adding a maintained library is implementation work, not permission to hand-roll a second scroll engine. Keep active selection and the focused row mounted; offer an accessible paginated full-text reading mode using the same endpoints if windowing interferes with assistive technology. Search is server-backed and never depends on browser Find over mounted rows.

Initial operational budgets to test, not asserted measurements: 20 thread summaries / 50 poses per request; no more than 150 full pose bodies mounted in the normal windowed reader; cache at most 500 retained bodies per active conversation with 5 inactive conversations kept as recoverable LRU windows. Do not evict selected text or a pending sent pose. Aggregate pages/search results avoid N+1 enrichment; include query-count tests and inspect representative SQL plans before claiming readiness.

Acceptance workload: 500 poses, 20 threads with one 250-reply thread, 2–6 paragraphs each, one 10,000-character pose, equal timestamps across a page boundary, a deleted parent, blocked/muted content and 20 incoming replies during historical reading. On the measured test machine record scroll/typing behavior and profile long tasks; avoid repeated main-thread tasks above 50ms during scrolling after data arrival. Do not turn an uncalibrated wall-clock threshold into a flaky unit test. Include a 2,000-pose stress run and record the actual machine/browser.

Keyboard: Tab follows visible controls; thread buttons expose `aria-expanded`/`aria-controls`; Enter/Space toggles; focus stays on the triggering header after collapse. Do not announce entire pose bodies repeatedly; a polite region announces concise new-activity counts. Mark actionable failures with appropriate alert semantics. Touch targets approximately 44px, reduced motion respected, themes maintain readable contrast, and 320px width / 200% zoom must not introduce horizontal page scrolling.

## 12. Reuse map and implementation boundaries

Inspected files below are a starting map; re-read their current versions in the implementation worktree. Do not copy the mockup's single-file DOM code into React.

| Existing area | Reuse/change |
| --- | --- |
| `frontend/src/game/GamePage.tsx` | Keep live composition root; own live context separately from reference selection; integrate sidebar/context and encounter tools. |
| `frontend/src/game/components/GameLayout.tsx` | Replace three columns with main + sidebar, independent scroll containment, responsive switching and resizing. |
| `GameWindow.tsx`, `ChatWindow.tsx`, `SystemLane.tsx` | Replace terminal fallback and raw notice lane with lifecycle/exploration/structured reader states and classified feedback. |
| `RoomPanel.tsx`, `FocusPanel.tsx`, room-panel components | Recompose into Here/inspector rather than rewriting gameplay behavior. |
| `CommandInput.tsx` and existing editor/composer components | Lift scoped drafts, parent/audience fields and acknowledgement lifecycle; retain formatting, attribution and action features. |
| `frontend/src/scenes/components/SceneMessages.tsx`, `PoseUnit.tsx` | Reuse pose body/reactions/actions; add thread groups and windowed/accessible reader adapters. |
| `useSceneInteractions.ts`, `useThreading.ts`, `queries.ts` | Preserve useful DTO conversion/filtering; replace scene-only assumptions and local-only grouping where new contracts require it. |
| `frontend/src/store/gameSlice.ts`, `threadTabsStorage.ts` | Separate recoverable history, live buffers, reading state and preferences; stop deleting all old-scene navigation state. |
| `frontend/src/hooks/useGameSocket.ts`, interaction/room handlers | Route typed updates to proper context; dedupe acknowledgements/echoes; prevent late connection responses from changing the active actor. |
| `frontend/src/combat/components/CombatRail.tsx`, scene detail integration | Mount the same encounter toolset within the single sidebar, with one map and persistent aftermath; retain GM permission gates. |
| `src/world/scenes/interaction_views.py`, filters/serializers/managers/permissions/services | Shared authorized history and new thread/context/read contracts; preserve language/identity and ephemeral rules. |
| `src/actions/definitions/communication.py`, player action doorway | Extend structured write acknowledgements/reply metadata; do not duplicate mechanics in view code. |
| `src/world/scenes/models.py`, partition SQL and aggregator migrations | New metadata/read tables and timestamp-aware reference integrity; new-column drift checks if Interaction changes. |

Suggested focused frontend modules: `PlayWorkspace`, `PlaySidebar`, `HistoryNavigator`, `InteractionReader`, `ThreadGroup`, `ReferenceHeader`, `usePlayReader`, `useScopedDrafts`, `playPreferences`. They should each own a real behavior, not a pass-through abstraction. Keep domain rendering in existing scene/room/combat components.

## 13. Delivery boundaries for the implementation agent

These are contract-level delivery slices, not a second committed step-by-step coding plan. The issue/spec is the durable design record. Create a worktree under `.claude/worktrees/` and follow repository AGENTS instructions when implementation begins.

1. **Reader contracts and fixtures:** DTOs, explicit thread/context metadata, canonical visibility, cursor/context/search/read behavior and acknowledged write extension. Demonstrate permitted older history, parent validation, idempotency and partition integrity. This establishes the contracts consumed by the UI.
2. **Workspace and lifecycle:** single sidebar, responsive layout, entry/exploration/ready/reference/stale/error states, classified notices, existing room/inspector integration, display preferences and scoped composer. No terminal route is reachable in the completed slice.
3. **Threaded/history reader:** scalable windowing, collapsed groups/poses, chronology preference, anchors/read gaps, search/context navigation and reference return. Demonstrate the full long-history workload rather than a handful of mocked messages.
4. **Scene actions and encounter integration:** existing action/consent/round widgets and combat rail in the live workspace, draft preservation, one tactical view, aftermath and urgent prompts independent of sidebar selection.
5. **Channel integration and final journeys:** integrate #3299's actual API when available; exercise identities/filters and notification preferences. Channel backend delivery is its own issue. Full layout editor and cross-device display preferences remain deferred. Finish frontend build, accessibility and CI parity checks.

The implementation agent must not decide to omit threading/history to make the task smaller, invent private-record retention, infer thread relationships by regex, parse terminal text for authoritative state, add account-name identities to channels, hardcode sample stats/combat actions, or delete existing scene features without mapping them into the new surface. If a domain/API contract is impossible against changed code, report the concrete mismatch against this spec before substituting behavior.

Release as a coherent `/game` experience after the mandatory journeys pass. A rollout flag may select complete old/new implementations during development, but it must not choose a terminal fallback inside the new experience. Preserve API compatibility for existing scene pages during transition. Do not deploy or remove the old path merely because this design document exists; publication remains separate from the authorized design work.

## 14. Acceptance and verification matrix

| ID | Scenario | Required result |
| --- | --- | --- |
| A01 | Fresh account, no entered character, entry failure, retry | Purposeful entry/error views; no account transcript or ready-on-socket-open state. |
| A02 | Enter quiet room, inspect person/object, travel | Room remains complete without a scene ID; only authorized actions; old draft recoverable and not retargeted. |
| A03 | Scroll main then sidebar | Each retains its independent position; no accidental outer transcript scroll. |
| A04 | 500 long poses, 20 threads, same timestamps | Stable deterministic pagination with no duplicates/missing boundary rows. |
| A05 | Reply to root and reply-to-reply | Correct explicit parent/root, shallow presentation, no recipient changes or excessive indentation. |
| A06 | Collapse thread; receive 20 replies | Thread stays collapsed, unread updates, reader and composer do not jump. |
| A07 | Read later pose while earlier thread is folded | Hidden replies remain unread; mark-all is explicit and snapshot-scoped. |
| A08 | Expand, resize text, load older page above viewport | Restore interaction and intra-pose anchor; sidebar position unchanged. |
| A09 | Search a phrase in older scene beyond 90 days | Explicit date range retrieves retained authorized result and surrounding context. |
| A10 | Open old whisper while drafting a room pose | Reference mode read-only; return restores live draft/audience/position; no historical send. |
| A11 | Deleted/blocked/unavailable parent and stale reference | Generic safe placeholder/error; remaining accessible thread readable; no hidden author/body/count leak. |
| A12 | New account inherits character with old whispers | Pinned private-party policy preserved across list, detail, search, snippets and counts. |
| A13 | Garbled spoken language, muted/VERY_PRIVATE content | Search and previews reveal no text the viewer cannot read; rules consistent with permitted detail access. |
| A14 | Send, lose ack, receive echo, retry | One accepted pose and action; pending text retained until resolved; newer draft not cleared. |
| A15 | Scene/room/persona changes while request is in flight | Response stays attached to original context; stale recipient/scene rejected without public fallback. |
| A16 | Ephemeral scene with >200 poses; reload/reconnect | Active buffer supports long play; no durable bodies; explicit unrecoverable-gap/temporary-history state. |
| A17 | Combat begins while editing and browsing History | Draft/reader survive; urgent prompt reachable; one map, one home per control, aftermath preserved. |
| A18 | Narrow width, mobile keyboard, 200% zoom, keyboard-only | Reader/sidebar/tools reachable; visible focus, labeled collapse controls, no horizontal page overflow. |
| A19 | Corrupt/unavailable storage, logout, account switch | Safe defaults, draft-state notice, no cross-account draft/navigation exposure. |
| A20 | Existing channels become available | #3299 identities/filtering/notifications respected; channel feed separated from IC and no second backend. |
| A21 | Retry old-page/search failure, switch thread mid-fetch | Prior passage preserved; late response cannot overwrite another conversation; retry recoverable. |
| A22 | Partition migration and cleanup | Fresh/existing PostgreSQL schemas accept metadata links; no invalid FK assumption or orphaned references after deletion. |

Frontend verification in implementation: `pnpm install`, `pnpm typecheck`, relevant `pnpm exec vitest run ...`, `pnpm build`, then `pnpm exec playwright test` from `frontend` (the configured E2E server uses the production preview build). Backend tests use `just test-affected` and supported `just test-fast` scopes, always via repository wrappers / `uv run arx test`; do not substitute bare pytest/Python. Scenes/partition cases need CI Postgres parity; do not run the full slow local parity suite or claim SQLite validates partition behavior. Do not bypass pre-commit/pre-push hooks. Update generated API schema/types and applicable ADRs alongside implementation.

Record actual test results and remaining failures in the implementation PR. The design prototype only verifies local presentation behavior; it cannot establish production privacy, reliable delivery or server performance.

