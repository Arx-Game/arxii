# Arx II: a narrative play workspace

Design proposal grounded in the local repository and the supplied screenshot. The accompanying interactive concept uses illustrative names, prose, locations, stats and encounter choices. It is not connected to the game. No application code has been changed.

## The product decision

Remove the terminal from every player-facing state. Entry, empty rooms, travel, roleplay, combat, disconnection and errors must each be designed experiences. The center of play is the evolving fiction and the player's contribution to it.

Narrative guidance means making the situation legible: where you are, who is available to interact with, what you can perceive, and which actions are possible. It should never prescribe a player's feelings, invent hidden knowledge, or turn open-ended roleplay into compulsory dialogue choices.

## Three presentations to compare

| Direction | Experience | Tradeoff |
| --- | --- | --- |
| **Narrative desk — recommended** | Stable surroundings at left, generous prose in the center, selected details and decisions at right. Restrained gold, warm stone or dark green-gray surfaces, serif scene titles and readable prose. | Requires strong prioritization of what earns space in the contextual pane. |
| Conversation lounge | Same underlying capabilities, with more compact, clearly bounded author messages and sans-serif prose. Familiar conversational rhythm for people coming from Discord. | Long literary poses can become a wall of bubbles; message density should be adjustable. |
| Reading room | Wide prose area, minimal persistent controls, details opening on demand. Suits long scenes and smaller laptops. | Surroundings and combat decisions are less continuously visible; urgent prompts must remain inline. |

Use the narrative desk as the default, with reading and density preferences. Treat these as presentations of one model, not separate clients. The current ADR-0111 explicitly calls for chat bubbles; adopting the editorial default would require a deliberate revision of that presentation decision while preserving its structured-feed and one-play-surface principles.

The prototype's design controls switch both the presentation and the moment in play: entry, exploration, scene and encounter. Normal controls let the reviewer move between rooms, select conversations, inspect people, open character details, write sample contributions and declare an example combat intent.

## The layout and what each area owns

**One compact header:** brand, World, Scene, Journal, and the current character/persona. Avoid stacking the marketing navigation, a second game header and a duplicate “Enter the world” call to action once playing. Account navigation remains available through the identity menu in implementation.

**Surroundings:** current location, conversation groups, observable people, nearby objects and exits. Location is always visible. Place-specific and private conversations have plain-language audience labels and separate unread indicators. Keep important scene-wide events visible even while reading a smaller conversation, without exposing private content. The prototype demonstrates the panes and threads; the scene-wide alert treatment remains an implementation item.

**The story:** a compact scene heading, readable authored contributions, occasional environmental beats, and an anchored composer. Author and time are secondary to the writing. Clicking a person or an object opens details without changing the story's route. No full-screen decorative image should push the actual roleplay out of view. Room art is optional; rooms without images must look complete.

**Context:** an inspector with one current focus and a clear way back. At rest it shows relevant, authorized scene context. Selecting a person shows their visible description and interactions; selecting an item shows what can be perceived and done; selecting yourself shows condition, relevant effects, stats and belongings. During an encounter it offers the current decision and one tactical view. Avoid nine equal-weight system tabs as the default answer to “what matters now?”

Context summaries must be authored or derived from facts the server permits this viewer to see. They must not expose GM-only story beats, concealed identities, other players' thoughts, or future consequences.

## The experience across states

1. **Entering:** a character card with a real entry action and last known location. Show entering, ready, retryable failure and reconnecting states. Do not call a character ready because a socket opened. Presentation work should proceed before the transport redesign.
2. **Exploring:** the room becomes the main content: evocative description, visible people, inspectable objects and exits with destination names. A quiet room gets a deliberate quiet state. An available scene can invite participation; permission and presence rules determine the real action. Merely looking at a scene must not silently enroll or record someone.
3. **Roleplaying:** the story takes precedence while surroundings remain available. Public room contributions, place conversations, whispers and OOC need distinct scopes. Selecting an audience changes the composer label, and the label stays visible before submission. Keep each draft and scroll position with its character, location/scene and audience. Never transfer a private draft into a public composer after moving or switching identities.
4. **Acting:** context menus and action forms offer authorized choices. A player describes intent, attaches an available action, reviews audience/target/cost/risk when applicable, then submits. Typed prose never has to double as a command parser. The prototype's action text illustrates placement only; production must submit typed action references and validated parameters.
5. **Combat:** preserve the room, roleplay history and composer. A contextual panel shows the actor's current decision, applicable resources/effects and the tactical layout. Resolution enters the fiction as a readable event with expandable mechanical detail. Do not move the player to another route. Show one map, including bystanders, and give each GM control one home. Aftermath remains readable after the encounter ends.
6. **Finishing:** separate leaving a scene from keeping a record. Preserve the existing explicit keep/discard agency. A journal may show authorized kept records and private notes; a prototype list must not imply that all observed RP is permanently archived.
7. **Disconnected or waiting:** preserve the visible world as stale context, label the connection state, and disable authoritative actions until resynchronized. Keep drafts. Use a clear retry control and reconcile pending submissions before allowing duplicate sends. Failure copy belongs beside the attempted action, without raw server output.

## Smaller screens and writing comfort

At desktop width use three deliberate areas rather than arbitrary floating windows. At intermediate widths keep surroundings plus story, opening context as a drawer. At phone width use explicit Surroundings / Story / Details controls, preserving the same location, thread, draft and scroll state. The current hidden desktop sidebars must have accessible replacements.

Support keyboard navigation, visible focus, adjustable prose size, sufficient contrast in both themes, reduced motion and long unbroken text. New arrivals should not steal focus or drag a reader to the bottom. Announce concise new-event counts to assistive technology, not an entire moving transcript. Preserve drafts when combat controls mount and when background data refreshes.

## What is already in the code

| Existing implementation | Design implication |
| --- | --- |
| `frontend/src/game/components/GameWindow.tsx:239` chooses `SceneMessages` only when `sceneFeed` exists; line 262 renders `ChatWindow` otherwise. `ChatWindow.tsx` explicitly uses black background and monospace. | The terminal is a default state, not merely a stylesheet accident. Replace the conditional terminal fallback with explicit entry, exploration and narrative states. |
| `frontend/src/hooks/handleRoomStatePayload.ts` stores room descriptions, characters, objects, exits, scene and hub information. `RoomPanel.tsx` already renders substantial room interactions. | Make the room a primary experience with existing structured data. Avoid scraping room descriptions out of text output. |
| `frontend/src/game/GamePage.tsx` already composes scene interactions, threading, places, consent and action attachment. | Recompose and refine existing capabilities rather than rewrite the game client wholesale. |
| `frontend/src/scenes/hooks/useThreading.ts` groups room, place, whisper and target interactions. `Interaction` distinguishes visibility receivers from public targets. | Much of conversation grouping exists. Arbitrary nested reply chains do not appear in the inspected interaction type; implement explicit parent/root references only if true reply threading is wanted. Public targeting is not privacy. |
| `frontend/src/scenes/hooks/useSceneInteractions.ts` fetches only with a scene ID and excludes socket interactions with null scene IDs. | Structured exploration and ambient activity need intentional handling outside named scenes. Do not force permanent scene creation just to obtain a renderer. Verify the ephemeral interaction delivery contract. |
| `FocusPanel.tsx` has a room/person/item focus stack. | Reuse the inspector behavior, with stronger hierarchy and accessible drawer variants. |
| `SceneDetailPage.tsx:436` mounts `CombatRail`; `GamePage` passes encounter flags to room badges, whose links lead to scene detail. | The full combat presentation still needs to be composed into live `/game` to fulfill the one-surface design. |
| `GameLayout.tsx:20` defines fixed desktop columns; both sidebars are hidden below `lg`. | Mobile needs navigation to the missing capabilities, not merely hidden columns. |
| `SystemLane.tsx` keeps raw messages behind a collapsible strip. | Replacing the terminal also means classifying useful feedback into notices, activity and actions. A collapsed raw log should not become the new player-facing terminal. |

These are observations of the local checkout, not a verified audit of the currently deployed server.

## Implementation order

**First: deliver the presentation foundation.** Introduce the narrative shell and explicit state views. Promote room data to exploration. Render structured narrative contributions regardless of whether the player has a named scene. Replace raw system output with appropriate notices and action feedback. Add a visible, useful quiet-room state. Reuse the existing inspector, threads and composer. Ship a coherent vertical slice from entry to room to one conversation, including mobile access.

**Next: unify interaction and scene tools.** Keep audience visible, preserve scoped drafts and scroll, attach actions as structured data, and bring encounter/aftermath presentation into the live play composition. Add context-specific character stats and item interactions. Keep server-driven permissions, intent events, flows and triggers authoritative; mockup labels and example choices must never become hardcoded gameplay rules.

**Then: harden entry and reconnect.** Replace a literal text `@ic` send with a typed character-entry operation using stable IDs, an explicit success/failure acknowledgement and an authorized initial state snapshot. Treat account authentication, character selection, world presence and socket connectivity as different states. The local backend already defines `@ic` with `ic` as an alias in `src/commands/account/character_switching.py`; the screenshot's rejection points to an unverified deployment/registration mismatch, not proof that the spelling is wrong. This work is necessary but secondary to the design effort requested here.

## Acceptance criteria

- A new player can enter, inspect surroundings, travel, join an available conversation, reply and inspect their character without typing a command.
- No player-facing state renders an ANSI transcript, account command help, raw protocol payload or console fallback.
- Quiet rooms and scene transitions retain a complete interface.
- Audience is explicit before every contribution; private content is filtered by the server and does not leak through search, summaries or unread metadata.
- A fight and its outcome remain in the same scene. Starting combat preserves the draft and does not duplicate the tactical map.
- On phones, the same surroundings, conversations, details and actions remain reachable.
- Reconnection cannot silently double-post; unacknowledged contributions remain distinguishable from delivered ones.
- Record retention continues to require the existing explicit choices.

## Prototype scope

The concept exercises local interaction and responsive presentation, not actual permissions, retention, backend rules, live updates or connection reliability. The sample contextual narration is hand-authored. The sample combat rules and character values are design fixtures. The implementation should obtain those from the existing domain systems.

