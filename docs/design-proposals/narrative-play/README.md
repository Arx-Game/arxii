# Initial narrative play designs

This snapshot preserves the first interactive concepts for replacing Arx II's browser terminal. These are design references, not an implementation or a settled visual specification. No production application code is changed by this snapshot.

## Decisions after the initial review

- **Firm:** remove the terminal from every player-facing web-play state. Entry, exploration, quiet rooms, active scenes, combat, and failures all need intentional interfaces. A reskinned or collapsed terminal does not meet the requirement.
- **Tentatively preferred:** the narrative workspace direction: meaningful surroundings, readable roleplay, visible audience and authorship, a persistent composer, and contextual character/object/action/encounter tools.
- **Provisional:** the original three-column arrangement, exact panel contents, typography, spacing, navigation and visual treatment. The screenshots are a starting point, not a pixel-perfect implementation contract.
- **New review requirement — long-form RP:** people regularly write several paragraphs per pose. The initial font is probably too large. Choose a smaller readable default, with adjustable font size, line height and message density. Test multiple consecutive long poses and long drafts, not only short chat samples. Do not silently truncate contributions; any collapse/expand behavior is an explicit reader preference.
- **New review requirement — writing width:** a central feed/composer between permanent left and right sidebars may be too narrow. Compare a wide narrative and writing column plus one scrollable sidebar containing the contextual sections. Collapsible/dockable sections and a reading mode are candidates. Preserve comfortable reading line length at very wide screens; do not simply stretch prose without bounds. The one-sided layout is a candidate for the default, not yet a final ruling.
- **OOC channels are expected:** decide where persistent public/org OOC channels live and how players control their visibility. Keep persistent channels distinct from scene-local OOC, room roleplay, private whispers and IC correspondence. Coordinate with [#3299](https://github.com/Arx-Game/arxii/issues/3299), which already calls for filtering, muting, ordering and notification controls so channels never crowd IC. Its proposed right-hand Channels tab is subject to the broader layout review, not a requirement to preserve two permanent sidebars.
- **Allow future customization:** separate panel content and data subscriptions from where panels are placed. Use stable panel identifiers and a layout-preference boundary with defaults and a reset path. Candidate settings include pane visibility/order/width, docking, font size, density and channel notifications. Exact controls and persistence scope can be iterated later; a full drag-and-drop dashboard editor is not a prerequisite for removing the terminal. Customization never changes audience or authorization and must not make urgent actionable prompts unreachable.
- **Priority:** remove the terminal and establish a coherent narrative experience first. Iterate on the precise look and organization. Typed character-entry acknowledgements and robust reconnect handling are important secondary work, not the focus of this design issue.

## Files

- [Initial narrative scene](arx-scene-desktop.png)
- [Exploring a location](arx-exploration-desktop.png)
- [Combat within the scene](arx-combat-desktop.png)
- [Phone presentation](arx-scene-mobile.png)
- [Conversation lounge alternative](arx-conversation-desktop.png)
- [Reading room alternative](arx-reading-desktop.png)
- [Standalone interactive preview](arx-play-preview.html): download and open locally. World/Scene navigation, conversations, inspection and writing operate only on example data. GitHub displays the source; it does not run the preview. The optional Codex design-control panel is not available in this standalone export; the alternative presentations and combat state are preserved in screenshots and the original source.
- [Original interactive fragment](arx-narrative-play.html): preserves the optional Codex controls for layout, moment and prose size.
- [Initial design brief](arx-play-design.md): code findings, proposed experiences, implementation sequence and acceptance criteria from before the follow-up review. **The review decisions above take precedence wherever the initial brief assumes a three-column default or larger prose.**

The illustrations use invented names, locations, prose, stats and encounter choices. They do not define gameplay rules or imply that unavailable data exists. Backend-authorized, data-driven actions remain authoritative. The source is a presentation study, not production code to transplant.

## Validation and limits

The original prototype was checked across 72 presentation/state/width/theme combinations, with additional checks for scoped drafts, local posts, private-thread separation in the fixture, inspection, travel, encounter declarations and phone pane access. These are prototype checks, not proof of live server privacy, reconnect correctness or production integration. Long-form typography and a one-sided sidebar remain design iterations requested by the reviewer; the original screenshots deliberately retain the initial design for comparison.

