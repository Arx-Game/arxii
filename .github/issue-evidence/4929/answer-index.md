# Answer index for the two open evidence items on PR 4934

Head recorded: 901c39c083c887ce5864672b528b2b40db092726 (confirmed with git rev-parse HEAD in the feature worktree after git pull --ff-only said up to date). Main compared: c432b02d53d9f65fed1a14d5893ce6a78c9b4c23 (origin/main fetched at recording time). Each run used a throwaway detached worktree and one new private Postgres test database (test_arxii_dfr4929c, built once with just build-test-schema, run with arx test --keepdb; no existing database touched). Head and main share it: the branch adds no migration. Both worktrees and the database are removed. Every JSON below carries `reviewed_commit` (and a `label` for item 7). The first round's files were moved to the scratchpad.

## Item 7: a staff-authored SERVICE-kind imbuing rite

Head sha: 901c39c083c887ce5864672b528b2b40db092726

Did: authored a SERVICE ritual named Quick Imbuing whose service function is the imbuing service (staff variant of the Rite of Imbuing). Ysmay holds the Quicksilver vow with its thread at vow level 1 and resonance to spend. Ran it once through telnet (`ritual Quick Imbuing thread=... amount=...`) and once through the web endpoint (POST /api/magic/rituals/perform/), imbuing from level 1 to 2 (a crossing) and from level 1 to the middle of level 1 (no crossing). Then ran the same four at origin/main.

Expected (from the issue and the coordinator's note): the rite line, then "Quicksilver is now level 2." and "Vow level 2: 4 pts of new picks." on a crossing; only the rite line within a level; and at main the old TypeError.

Saw at head:
- Telnet crossing: "You perform Quick Imbuing.\nVow level 2: 4 pts of new picks."
- Web crossing: HTTP 200, same message, `opened_pick_levels` [2], `new_picks` [{level 2, points 4}], result new_level 20.
- Within level (telnet and web): "You perform Quick Imbuing." and no picks line.
- Not met: no "Quicksilver is now level 2." line on a SERVICE rite. That line is added only by the canonical Rite of Imbuing's finisher (the CEREMONY variant, checked in the previous round). The SERVICE variant's message is the generic "You perform X." plus the new-picks lines, so the expectation as stated does not hold; the new-picks line, which is the slice's requirement, does.

Saw at origin/main (same four runs): every run fails. Telnet raises `TypeError: spend_resonance_for_imbuing() got an unexpected keyword argument 'ritual'` (dispatch_ritual forwards ritual= to the service function); the web request returns HTTP 500 "Internal server error". At head the service function accepts and ignores the forwarded keyword (`**_ritual_dispatch_kwargs`), which is why head returns.

Files:
- item7-head-telnet-service-rite-crossing-1-to-2.json
- item7-head-web-service-rite-crossing-1-to-2.json
- item7-head-telnet-service-rite-within-level-1.json
- item7-head-web-service-rite-within-level-1.json
- item7-main-telnet-service-rite-crossing-1-to-2.json
- item7-main-web-service-rite-crossing-1-to-2.json
- item7-main-telnet-service-rite-within-level-1.json
- item7-main-web-service-rite-within-level-1.json

## Item 8: telnet names, same-named picks, catalog ids, joining

Head sha: 901c39c083c887ce5864672b528b2b40db092726

### 8a. A pick name containing "in", and naming a covenant

Did: Ysmay holds Quicksilver (vow level 2, The Quicksilver Hall) and Ember (vow level 1, The Ember Court). Ran `vow pick Cut in Two`, `vow pick Bleeding Cut in The Quicksilver Hall`, `vow pick Read the Feint in Nowhere`, `vow picks`, `vow picks in The Ember Court`, `vow picks in The Quicksilver Hall`, `vow picks in Nowhere Hall`, `vow pick Cinder Step in The Ember Court`, `vow pick Cinder Step in The Quicksilver Hall`, `vow pick Cinder Step`.

Expected: "Cut in Two" is a pick, not a covenant named Two; a trailing "in" phrase names a covenant only when she belongs to one by that name; `in <covenant>` narrows the list; an unknown covenant is refused plainly.

Saw: "You take Cut in Two. Level 2: 1 of 4."; "You take Bleeding Cut. Level 2: 4 of 4." (covenant honoured); "Your vow offers no pick named Read the Feint in Nowhere." (Nowhere is not her covenant, so the whole phrase is the pick name); `vow picks` lists Ember then Quicksilver; `in The Ember Court` lists only Ember, `in The Quicksilver Hall` only Quicksilver; "You are not a member of a covenant named 'Nowhere Hall'."; "You take Cinder Step. Level 1: 1 of 4."; "Your vow offers no pick named Cinder Step." when the named covenant's vow does not offer it; "You have already chosen Cinder Step." Rows chosen at the end: Bleeding Cut, Cinder Step, Cut in Two.

File: item8-telnet-pick-names-and-covenants.json

### 8b. Two same-named picks across the anchor and the sub-role

Did: Ysmay holds the sub-role Quicksilver Duelist (anchor Quicksilver); both offer a level 1 pick named Riposte (prices 2 and 1). Ran `vow pick Riposte` and `vow pick riposte`, read the catalog, then chose the sub-role's Riposte by id through the web dispatch.

Expected: a name that two of her vows offer is refused with a message saying so and nothing is chosen; the id still disambiguates.

Saw: "Your vow offers two picks named Riposte; choose one on your sheet." (and the same for the lower-case spelling); zero picks chosen after both; the catalog lists both (vow Quicksilver price 2, vow Quicksilver Duelist price 1); the web dispatch by id returned "You take Riposte. Level 1: 1 of 4." and the row chosen belongs to Quicksilver Duelist.

File: item8-same-named-picks.json

### 8c. Catalog with a malformed or foreign sheet id

Did: GET /api/covenants/character-roles/vow-picks/ with character_sheet set to abc, the superscript two character (U+00B2), missing, 0, empty, and her real sheet id, as her own account and as another account; plus one request with no login.

Expected: malformed or missing id is 400 for any requester; another account's real sheet is 404; her own is 200.

Saw: all five malformed or missing values gave 400 "character_sheet is required." for both accounts (no 500 for the superscript); her own sheet id gave 200 with the catalog; another account's real sheet id gave 404 "Not found."; no login gave 403.

File: item8-catalog-sheet-ids.json

### 8d. A join that rolls back versus one that commits

Did: Ysmay's Warden vow thread already stands at vow level 2. Wren fires the Covenant Induction rite, in one run with a later step of the same transaction raising after the membership row was created (the external-act step patched to raise), in the other normally. The send is tied to commit, so on-commit callbacks were run for both.

Expected: the rolled-back join leaves no membership and tells Ysmay nothing; the committed join tells her about levels 1 and 2.

Saw: rolled back: the fire raised the induction error, no membership row, Ysmay told nothing, no new-picks line, 0 commit callbacks. Committed: membership exists, Ysmay told "[NARRATIVE] Vow level 1: 4 pts of new picks." and "Vow level 2: 4 pts of new picks.", 1 commit callback.

Files:
- item8-join-rolled-back.json
- item8-join-committed.json
