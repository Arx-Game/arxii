# Review evidence: #4558 Mission Studio: add, delete, route and check a mission graph

- Reviewed revision: `cd2f0c0f93b4714dadba53935f8c851c6ccce2c2`
- Reviewer: Claude (Opus 5.5), following tools/skills/real-testing/SKILL.md; every screenshot read by eye against the spec's scope items
- Reviewer verdict: PASS
- Application/build identity: this worktree's own Django server (`evennia runserver 127.0.0.1:4158`, restarted after the last Python change) and its own Vite dev server on localhost:3158 proxying to it, both serving cd2f0c0f9; never the shared server
- Environment: devcontainer workstation (10 GB); scratch database scratch_pmc_20261023T024812Z_42806, restored from the newest production dump arxii-20261022T033018Z.sql.gz by `tools/prod_migration_check.sh --keep` (RESULT PASS, nothing pending); Playwright Chromium headless, script driven through the Studio pages only
- Viewports/themes: 1400x1000, light theme only
- Approved design: no demo for this issue; the approved design is the spec's Scope list in the #4558 issue body (items 1 to 16), ruled in chat by the maintainer
- Visual review: completed; each screen of the Studio this change touches (graph page, add node, node page dialogs, option page route editor, delete confirmation) read against the scope items it implements
- Visual verdict: PASS
- Screenshots: ![production mission with missing tiers](docs/reviews/4558/01-merchants-debt-graph.png) ![option page routes by name](docs/reviews/4558/02-merchants-debt-option-routes.png) ![missing tiers added](docs/reviews/4558/03-merchants-debt-missing-tiers-added.png) ![production mission clean](docs/reviews/4558/04-merchants-debt-graph-fixed.png) ![empty mission](docs/reviews/4558/05-new-mission-empty.png) ![add option dialog](docs/reviews/4558/06-add-option-dialog.png) ![all tiers](docs/reviews/4558/08-new-option-all-tiers.png) ![vault unreachable](docs/reviews/4558/09-vault-unreachable.png) ![success to vault](docs/reviews/4558/10-success-to-vault.png) ![graph clean](docs/reviews/4558/11-graph-clean.png) ![delete confirmation](docs/reviews/4558/12-delete-vault-confirm.png) ![after delete](docs/reviews/4558/13-after-delete-graph.png)
- Comparison notes: the Problems panel shows nothing while the check loads and then either the problems or "No problems found."; routes that share a source and destination are drawn as one arrow naming every tier (a change made during this pass, because five stacked arrows overprinted their labels); a check option's tiers are listed by the success level they carry, lowest first, in the merged label and in the order the server returns routes on the option page.
- Tested interactions: log in on the React login page; open a production mission's graph; follow a problem link to the option page; "Add the missing tiers"; reopen the graph; create a mission through the existing create endpoint; "Add node" on the empty graph (first node becomes the entry node); click the node on the graph; "Add option" with kind Check and a check type; "Add the missing tiers" on the new option; "Add node" for a second node; set the Success route's "Leads to" to the new node and "Save route"; reopen the graph; click the second node; "Delete node", read the confirmation, confirm; read the routes back over the API.
- Fixture/live boundary: live server and live database (a production copy). Outside the pages: one staff account made in `evennia shell` on the scratch database with its email marked verified and a player record added (the bare account had none), the new mission's template created by POST to the existing create endpoint (template creation is not this change), and "The Merchant's Debt" reset once in the shell (its two added routes deleted) so this final run started from production's state, followed by a server restart.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| S4-missing-tiers-on-production | PASS | "The Merchant's Debt" (production mission 4) lists `"option-2" has no route for: Critical Failure, Critical Success.`; its option page lists Failure, Partial Success and Success routes by name, each leading to "Mission ends"; one click on "Add the missing tiers" added Critical Failure and Critical Success and the graph then read "No problems found." 01, 02, 03, 04 | none needed |
| S4-S5-empty-mission | PASS | A new mission's graph reads "This mission has no entry node, so nobody can start it." with an "Add node" button; the first node added ("gate") showed "(entry)" and its Entry node switch read checked. 05 | none needed |
| S6-add-option-by-kind | PASS | "Add option" with kind Check shows a Check type select; the option "force-the-lock" was created and its page opened with no routes; "Add the missing tiers" created all five tier routes, each leading to "Mission ends". 06, 08 | none needed |
| S4-unreachable-node | PASS | After "Add node" for "vault": `Nothing leads to "vault" from the entry node.`, and the vault box carries the warning mark and border. 09 | none needed |
| S10-route-editor | PASS | On the option page the Success row's "Leads to" was set to "vault" and saved; the graph then drew one arrow "force-the-lock · Success" into vault, one arrow naming the other four tiers into "Mission ends", and "No problems found." 10, 11 | none needed |
| S1-node-click | PASS | Clicking the "gate" and "vault" boxes on the graph opened their node pages (the script reached both node pages only by clicking the graph). 06, 12 | none needed |
| S8-delete-confirmation | PASS | "Delete node" on vault: "These will become a mission ending · gate: force-the-lock · Success"; after confirming, the page returned to the graph showing one arrow naming all five tiers into "Mission ends". 12, 13 | none needed |
| S8-delete-reads-back | PASS | The routes API right after the delete returned all five routes with target_node null (the Success route included), so the Studio reads the route into the deleted node as an ending at once, with no restart. pass log line "routes after delete" | none needed |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Problems panel | One plain line per problem, linking to the option or node; "No problems found." when clean | MATCH | 01-merchants-debt-graph.png, 04-merchants-debt-graph-fixed.png, 09-vault-unreachable.png |
| Mission ends box | One dashed box that every ending arrow points at, drawn only when something ends the mission | MATCH | 01-merchants-debt-graph.png, 11-graph-clean.png |
| Arrow labels | Option key and tier names, never a database id | MATCH | 11-graph-clean.png, 13-after-delete-graph.png |
| Node warning | A node with a problem carries a warning mark and border | MATCH | 09-vault-unreachable.png |
| Add node and Add option dialogs | A key field, the kind, and the fields the kind requires; no help sentences | MATCH | 06-add-option-dialog.png |
| Route rows | Tier and destination by name, "Mission ends" as a destination, Save route and Delete route | MATCH | 02-merchants-debt-option-routes.png, 03-merchants-debt-missing-tiers-added.png |
| Delete confirmation | Names each link that becomes a mission ending; no question in the text | MATCH | 12-delete-vault-confirm.png |

## Findings fixed during this pass

1. "Add node" sent no conflict mode, so every new node was refused with a 400 (fixed in 938d215af; the unit tests had mocked the request).
2. "Add option" could make only branch options, because the server requires a check type, risk level or act for the other kinds and the dialog did not ask; the act was not in the API at all (fixed in 34462a576 and f360c30b2).
3. The Problems panel said "No problems found." while it was still loading, and parallel arrows overprinted their labels (fixed in c3a67c91a and cd2f0c0f9).

## Unresolved findings

None
