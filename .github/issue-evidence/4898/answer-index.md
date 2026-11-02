# Evidence answer index, PR 4917, round 1 open items

Head sha for every "after" run: 59e7cea70c67ec37057f24b75308f29e6ed10824 (branch feature-4898-natural-weapons-and-martial-arts-a-speci after `git pull --ff-only`).
Every JSON file carries `reviewed_commit` (that sha) and `ran_at_commit` (the sha of the checkout the run happened in). The "before" runs of items 13 and 14 ran at origin/main d97150191a353ea3366066b41b3de51157635600 and say so in `ran_at_commit`.

How: two throwaway detached worktrees, each with its own new Postgres test database built by `just build-test-schema` (test_arxii4898head for the head, test_arxii4898main for origin/main; no existing database touched). Each item was recorded by a throwaway test through the real seam named below, with the results written as JSON. Test files and worktrees are removed afterwards. Item lists are every in-play item the character holds, with where it is worn.
Fixture names: the journeys' "Khati Claws" gift and template, "Hobb", "Ysmay", "Wren"; extra items are plain factory items. Anything faked is said in the item.

## Item 2. Gaining the claws

Expected: the claws are made and equipped once per character and gift (spec), however the gift arrives and however often it is granted again.

- **learn technique transcript.** Did: Hobb (no claws) typed `learn gift`, `learn technique` for the gift's first technique, and `learn technique` for a second, in the telnet command handler. Saw: "Unlocked Khati Claws for 10 XP." with no items; "You learn Rake." with one Khati Claws equipped at left_hand/skin and right_hand/skin; "You learn Swipe." with still one pair. File: `item2-learn-technique-telnet.json`.
- **staff PATCH species.** Did: a staff account PATCHed `/api/character-sheets/<pk>/staff-edit/` with a species whose gift names the claws, then sent the same PATCH again. Saw: 200 both times; items before: none; after the first: one equipped pair; after the repeat: the same one pair. File: `item2-staff-species-patch.json` (status, species and natural_weapons fields of each response, and the response's top-level keys).
- **repeat grant.** Did: `grant_gift_to_character` three times (service call; the two seams above are the player and staff ones). Saw: one pair after the first call and after each repeat. File: `item2-repeat-grant.json`.

## Item 4. Paths that could take the claws off the character

Expected: each refuses with "That is part of the body and cannot be removed." (or, for a system sweep, leaves them alone), and afterwards the claws are still held and equipped at both hand skin slots. Each file also holds a control (a plain item through the same path) so a refusal is not just a broken path.

- **fence sale.** Seam: web dispatch of the action `market_sell_fence`. Control: a plain dagger sold ("The fence counts out 40 coppers for Old Dagger. No names."). Claws: success false, "That is part of the body and cannot be removed." Items after: claws present, equipped. File: `item4-fence-sale.json`.
- **org vault deposit.** Seam: web dispatch of `vault_deposit` in a room with a bank. Control: a signet ring deposited ("Signet Ring is now in House Coffers's vault."). Claws: success false, same message; claws still equipped. File: `item4-org-vault-deposit.json`.
- **boon ask.** Seam: REST POST to the scene action-requests endpoint as the asker's account (pointer knowledge faked, as the repo's boon tests do). Control: an ask for a plain dagger, 201. Claws: 400, "That is part of the body and cannot be removed."; claws unchanged. File: `item4-boon-ask.json`.
- **boon fulfilment.** SERVICE CALL ONLY: `fulfill_boon(boon)`. A boon naming the claws cannot be created through the ask (refused above), so the row was written directly, standing for one that predates the refusal. Control: a dagger boon fulfilled, the dagger moved to the asker. Claws: `ValidationError` "That is part of the body and cannot be removed.", `fulfilled_at` None, claws still with the target. File: `item4-boon-fulfilment.json`.
- **recycling.** Seam: REST POST `/api/items/inventory/<id>/recycle/` as the owner (`recycle_item` is not a web-dispatch action, so the REST route the wardrobe calls). Control: a cracked buckler recycled, 200. Claws: 400, `non_field_errors` "That is part of the body and cannot be removed."; claws still equipped. File: `item4-recycling.json`.
- **confiscation sentence.** SERVICE CALL ONLY: `schedule_sentence(case)`, the post-verdict dispatcher for a CONFISCATION sentence; no player command runs it. Saw: the traveller's pack moved to the brig room; the claws stayed on the accused, still equipped. File: `item4-confiscation-sentence.json`.
- **estate settlement.** SERVICE CALL ONLY: `execute_settlement(sheet, via=READING)` for a dead character whose will leaves the residue to an heir. Saw: the signet ring went to the heir; the claws stayed with the deceased, still equipped; settlement status "settled". File: `item4-estate-settlement.json`.
- **stake forfeit.** SERVICE CALL: `record_outcome_tier_completion` (what marking the beat failed calls), firing the LOSS branch of two item stakes with forfeit set, one on a plain locket (control), one on the claws. Saw: the locket row destroyed and held by nobody; the claws row not destroyed and still held; the writer logged "stake 3's subject_item is a natural weapon; skipping." (no player-facing text exists on this path). File: `item4-stake-forfeit.json`.
- **rite gifts.** Seam: web dispatch of `worship_rite` with `item_names`, in a live scene at a shrine. Control: a plain item given up ("You gave up Ash Offering; it meant nothing to the rite."). Claws: success false, "That is part of the body and cannot be removed."; claws still equipped. File: `item4-rite-gifts.json`.
- **shrine sacrifice.** Seam: telnet `sacrifice`. Control: "You sacrifice Ash Offering at Ombrin's shrine. No meaning points: given up, no roll, no favor." Claws: "That is part of the body and cannot be removed."; the being's resonance pool unchanged (100). File: `item4-shrine-sacrifice.json`.
- **ceremony offering.** Seam: telnet `ceremony/blessing` then `ceremony/offering`. Control: "The offering is consumed: Ash Offering." Claws: "That is part of the body and cannot be removed."; claws still equipped. File: `item4-ceremony-offering.json`.

## Item 5. Losing the gift

Expected: the claws go with the gift, from every path that removes a gift; never otherwise.

- **gifts API DELETE.** Did: the owning player, then a staff account, sent DELETE `/api/magic/character-gifts/<id>/`. Saw: player 403 with the claws untouched; staff 204, after which the character holds no items, the gift row is gone and no Khati Claws item row exists anywhere. File: `item5-gifts-api-delete.json`.
- **gift admin delete.** Did: a superuser opened the CharacterGift delete page (200) and confirmed (POST post=yes). Saw: 302; items none, gift row gone, no claws row anywhere. File: `item5-charactergift-admin-delete.json`.
- **beta reset.** SERVICE CALL: `wipe_pristine_world(execute=True, ...)` with its four guards satisfied (what the beta_reset command calls). Two characters: one whose gift came by training (a play-time origin), one whose gift is a species grant. Saw: the trained character lost the gift row and holds no items; the species-granted character kept the gift and the equipped claws. File: `item5-beta-reset.json`.
- **NPC copy.** Did: the owning GM POSTed `/api/roster/npcs/<id>/copy-section/` (section powers) so a clawed NPC copied the powers of one with no gift. Saw: 200; the clawed NPC's gift row and claws are gone, no claws row anywhere. File: `item5-npc-copy.json`.
- **deleting the character.** SERVICE CALL: `Character.delete()`, on an unpuppeted character (Evennia's delete of a puppeted one calls `account.characters.remove`, which this test environment's account does not support). Saw two cases. A character holding the gift the normal way: the database refuses with `ProtectedError` for the gift's Thread. The same refusal happens on origin/main for a character holding any gift with no natural weapon involved (`item5-delete-character-with-gift-before-on-main.json`), so it is not caused by this branch. A character with the claws and no gift Thread: deleted, and no claws row remains anywhere. File: `item5-delete-character.json`.
- **deleting the sheet in the admin.** Did: POST `/admin/arxii/charactersheet/<pk>/delete/` with post=yes for two sheets. Saw: the sheet holding the gift with its Thread: 200, the protected-objects page, nothing deleted, claws kept; the sheet with claws and no Thread: 302 and no claws row remains. File: `item5-delete-sheet-admin.json`.

## Item 6. Claws beside a held sword and gloves

Expected: a held sword and gloves go on beside the claws; claws cover no skin, so the sun and marking readouts with claws on equal those with claws off.

Did: one character with a burn-scar marking on the left hand, in an outdoor room with the game clock pinned to day, read six states: claws off, claws on, `wear Longsword`, `remove Longsword`, `wear Kid Gloves`, `remove Kid Gloves` (telnet). Readouts: the equipped list, `covered_regions`, `felt_sun_exposure`, and the marking's `marking_is_concealed` and `visible_markings_for` a stranger.
Saw:
- claws off and claws on, nothing else worn: covered regions none, sun residual 10 (coverage 0) in both, marking visible in both.
- "You equip Longsword.": sword at right_hand/base beside the claws at left_hand/skin and right_hand/skin; covered regions right_hand only; sun coverage 1, residual 9; marking (left hand) still visible.
- "You equip Kid Gloves.": gloves at left_hand/base and right_hand/base beside the claws; covered regions both hands; sun coverage 2, residual 8; the marking concealed, and not visible to a stranger.
- After each `remove`, the readouts return to the claws-only values.
The sword and the gloves fill the same right-hand base slot, so they were worn one after the other, not together; I did not record trying both. File: `item6-claws-beside-sword-and-gloves.json`.

## Item 12. Required content with two gifts naming one template

Did: a superuser fetched the real `/admin/_ops/required-content/` with one gift naming a template, then with a second gift naming it too.
Expected: the row names both gifts.
Saw: with one gift, the row sits under "present" ("Natural weapon templates: Unarmed, skin-layer slots, no durability, one gift"); with two, it is listed as missing with "Shared Claws: named by more than one gift (Blood of the Hunt, Wolfsong), so a holder of both gets a second pair that cannot be worn." Files: `item12-required-content-two-gifts.json`, `item12-required-content-row-two-gifts.html` (the row only, trimmed).

## Item 13. A player writing gift and anima rows

Did: the same test, as the player's own account (not staff), on origin/main and at the head: POST `/api/magic/character-gifts/` with their own character and a gift, then PATCH `/api/magic/character-anima/<id>/` with `{"current": 999}` (anima started at 3 of 10). The gift is a plain minor gift in both runs (claws need this branch's field).
Expected: main accepts the gift write (201); the head refuses both (403).
Saw on origin/main (d97150191): POST 201, a CharacterGift row for the player with origin character_creation; PATCH 500 "An unexpected error occurred", with `current` already 999 afterwards (written, then the response failed). Files: `item13-player-writes-before-on-main.json`.
Saw at the head (59e7cea70): POST 403 "You do not have permission to perform this action." and no gift row; PATCH 403 and anima still 3. File: `item13-player-writes-at-head.json`.

## Item 14. Before and after for the three fixes

Same fixture file on both checkouts; "before" is origin/main d97150191, "after" is the head 59e7cea70.

- **(a) a faceted piece in two slots.** `passive_facet_bonuses` for a Wolf-faceted piece (+2 a shown level, thread level 10). Plate armour over torso and left arm: before 4, after 2. A two-handed sword in both hands: before 4, after 2. Control, a one-handed sword in one slot: 2 before and after. Files: `item14a-passive-facet-total-before-on-main.json`, `item14a-passive-facet-total-after-at-head.json`.
- **(b) the covenant role weapon_damage bonus.** `covenant_role_bonus` for an engaged role, with the role's bonus pinned to 10 and the gear stat to 0 (as the repo's own unit test pins them). A two-handed weapon in two slots: before 20, after 10. Control, a one-handed weapon in one slot: 10 before and after. Files: `item14b-covenant-role-weapon-damage-before-on-main.json`, `item14b-covenant-role-weapon-damage-after-at-head.json`.
- **(c) staging the claws on the trade table.** Claws cannot exist on origin/main (no Gift.natural_weapon_template, no ItemInstance.natural_weapon_gift), so the "before" is the head with the trade action's fix undone: the one name `NaturalWeaponNotRemovable` inside `actions.definitions.trade` swapped for an unrelated exception class, which is the action's pre-fix except tuple. Without the fix: `world.items.exceptions.NaturalWeaponNotRemovable` propagates out of `stake_item` through `StageTradeItemAction.execute` and the dispatcher (the last frames are in the file); claws unchanged. At the head: success false, "That is part of the body and cannot be removed."; claws unchanged. File: `item14c-trade-stake-claws.json`.

## Not run, and why

- Item 14(c) on origin/main itself, for the reason above.
- Item 6 with the sword and gloves worn at the same time (they share the right-hand base slot).
- Items 1, 3 and 7 to 11 of the evidence check were not in this request.

## Files

All under `.github/issue-evidence/4898/`: `answer-index.md`, `item2-learn-technique-telnet.json`, `item2-staff-species-patch.json`, `item2-repeat-grant.json`, `item4-fence-sale.json`, `item4-org-vault-deposit.json`, `item4-boon-ask.json`, `item4-boon-fulfilment.json`, `item4-recycling.json`, `item4-confiscation-sentence.json`, `item4-estate-settlement.json`, `item4-stake-forfeit.json`, `item4-rite-gifts.json`, `item4-shrine-sacrifice.json`, `item4-ceremony-offering.json`, `item5-gifts-api-delete.json`, `item5-charactergift-admin-delete.json`, `item5-beta-reset.json`, `item5-npc-copy.json`, `item5-delete-character.json`, `item5-delete-character-with-gift-before-on-main.json`, `item5-delete-sheet-admin.json`, `item6-claws-beside-sword-and-gloves.json`, `item12-required-content-two-gifts.json`, `item12-required-content-row-two-gifts.html`, `item13-player-writes-before-on-main.json`, `item13-player-writes-at-head.json`, `item14a-passive-facet-total-before-on-main.json`, `item14a-passive-facet-total-after-at-head.json`, `item14b-covenant-role-weapon-damage-before-on-main.json`, `item14b-covenant-role-weapon-damage-after-at-head.json`, `item14c-trade-stake-claws.json`. No PNGs were needed for these items.
