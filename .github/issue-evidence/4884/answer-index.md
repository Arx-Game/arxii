Answers to the open evidence-challenge claims, issue 4884 (PR 4890)

Reviewed commit: c1a2a8730 (the tip of the branch when I started; checked out in a throwaway detached
worktree with its own Postgres database, built from that commit's models; both removed afterwards).
No source was edited. Everything below is a real run through the code, not a mock of it:
- Strike: the combat_strike web action through dispatch_player_action, resolved by resolve_round.
- Defense: a real NPC Blade blow in resolve_round; the PC's real Parry check, forced to Partial Success.
- Readbacks: the REST endpoints /api/checks/consequence-outcomes/ and /api/interactions/ as Mira's
  account.
- Renders: the real CombatTurnPanel in headless Chromium, fed those recorded payloads.
- Admin pages: the real Django admin through the test client, styled with the admin's own CSS, with
  the admin's JavaScript stripped from the saved copy.
The forced parts: each roll's outcome name (Strike hit and damage Success, defense Partial Success).
Test data: factory-built style, character, weapon and Blade. Names like trait_51 or CheckType17 in the
technique files are factory names, not product content.
The fixture round: Mira has The Daring Dance (Magic skill rating 20, hit stat Strength, evasion defense,
armor share 5 of 10, lists One-Handed Melee and Light Armor, works with the vow Quicksilver). She has
Melee Combat 25 and Dodge 15, wields a one-handed "Steading longsword", wears light armor, and the Blade
strikes her once in the round.

ITEM 2. A Strike with a LISTED weapon
Did: Mira Struck the Blade with the listed one-handed sword, then resolved the round.
Expected (from the spec and the 2026-11-01 rulings): the Strike hit roll adds the style skill (weight 1) and
uses the style's hit stat; the Last Outcome hit card shows the style skill row with its rating, and the hit
stat row.
Saw: the hit roll's kwargs had extra_traits = The Daring Dance weight 1 and stat_override = strength. The
readback hit breakdown: Melee Combat 25 "strike skill for one-handed melee"; Strength "the style's hit
stat"; The Daring Dance 20 "style skill" (lapsed false); result "Hit, fair". The render shows the style row
with 20, not struck.
Files: round-listed.json (full recording: roll kwargs, encounter payload, readback), readback-listed.json
(only the roll kwargs and breakdowns), lastoutcome-listed-desktop-dark.png,
lastoutcome-listed-desktop-light.png, lastoutcome-listed-phone-dark.png, lastoutcome-listed-phone-light.png

ITEM 5. A defense roll in LISTED armor
Did: same round, the Blade struck Mira in the light armor the style lists.
Expected: the defense breakdown shows the style skill with its rating, not struck, plus the armor share.
Saw: readback defense breakdown "Defense against Blade": Dodge 15 "defense skill"; The Daring Dance 20
"style skill" (lapsed false); "Armor, 5 of 10 / the style's armor share"; result "Partial Success, 8 damage".
The render shows the style row unstruck with 20.
Files: the same four files as item 2 (the defense card is the first card in each Last Outcome image).

ITEM 6a. A held vow NOT on the style's list lapses the Strike and the defense roll, each naming the vow
Did: same style, which lists only the vow Quicksilver; Mira swore the vow Bulwark (engaged with a thread); same
Strike and same Blade blow.
Expected: the style skill stops counting on both rolls, and each breakdown names the vow as the reason; the
hit stat still applies; the armor share is unchanged.
Saw: the Strike hit roll's kwargs had extra_traits empty (stat_override strength). Readback hit card: The
Daring Dance, no rating, lapsed true, detail "Bulwark is not this style's vow"; Strength row still there.
Readback defense card: The Daring Dance lapsed true, "Bulwark is not this style's vow"; "Armor, 5 of 10" still
counted, 8 damage as in the listed run. The render shows both style rows struck through with that reason.
Files: round-vow.json, readback-vow.json, lastoutcome-vow-desktop-dark.png, lastoutcome-vow-desktop-light.png,
lastoutcome-vow-phone-dark.png

ITEM 6b. A technique hit roll
Did: Ysmay (a Path with a technique skill) declared a technique through dispatch_player_action holding a
one-handed weapon the style lists (the style lists One-Handed Melee, hit stat Strength), and resolve_round ran.
Techniques record no breakdown row, so this was captured from the real roll call: a spy wrapped around the
perform_check that resolve_round calls kept the kwargs it received, then called the real function.
Expected: the style skill is added to the roll's extra traits alongside the Path's technique skill, and the
style's hit stat is NOT imposed on a technique.
Saw: extra_traits received = the Path's technique skill (weight 1.00) and The Daring Dance (weight 1);
stat_override received = agility, which is the held weapon's own stat. The style's hit stat, strength, was not
used. (With a weapon in hand the roll's stat is that weapon's, as before this slice; with no weapon, see 6c.)
File: technique-b-listed-weapon.json

ITEM 6c. A weaponless cast keeps the style skill
Did: Ysmay cast with no weapon in hand; the style lists only Two-Handed Melee. Same spy.
Expected: with no weapon there is nothing to test, so the style skill still counts and the technique rolls its
own check's stat (no stat override).
Saw: extra_traits received = the Path's technique skill and The Daring Dance weight 1; stat_override received =
null, so the technique's own check stat applies.
File: technique-c-weaponless.json

ITEM 9. The scene feed after an NPC blow
Did: in the item 2 round, read GET /api/interactions/?scene=SCENE_ID as Mira after resolve_round, and spied the
interaction send seam (interaction_services._send_to_objects) while the round resolved to catch the live frame.
Expected: the Narrator ACTION row for the Blade's blow, "Blade strike at Mira" (the threat name, "at", the
target), is in the feed and was also pushed live (a row only the refetch showed would appear after the fact).
Saw: the feed readback has row 28, persona Narrator, mode action, content "Blade strike at Mira", target
persona set to Mira's. The send seam received the same row (id 28, same content, mode action) addressed to
the room contents Mira and Blade, before the other three rows of the round (Narrator outcome, Mira's "Strike
at Blade" action, Narrator outcome). The frame is captured at the point the payload is handed to each room
object's msg(), not on a browser websocket; I did not render the scene feed component.
File: feed-narrator-action-row.json (the readback row, the live frame, and both orders); the full readback and
all frames are in round-listed.json under feed_readback and live_frames_captured_at_the_send_seam.

ITEM 11. The Gear kinds choice list, and a rejected save of a kind that is neither weapon nor armor
Did: opened a style's change page as a superuser and read the options of the Gear kinds select (the saved row
and the Add-another template row). Then posted the page's own form back unchanged plus one new Gear kinds row
with kind "jewelry" (Save and continue editing).
Expected: only weapon and armor kinds are offered, and a kind outside them is refused with a form error and
not saved.
Saw: offered, in order: Light Armor, Medium Armor, Heavy Armor, Robe, One-Handed Melee, Two-Handed Melee, Ranged,
Thrown, Shield, Lance, Unarmed. Jewelry, Clothing and Other are not offered. The POST answered status 200 (the
form shown again) with "Please correct the errors below." and the row error "Select a valid choice. jewelry is
not one of the available choices." Rows before 1, after 1: nothing saved. The error is the only error on the
page.
Files: gear-kinds-offered-options.json, gear-kinds-rejected-post.json, gear-kinds-change-page.html,
gear-kinds-rejected-post.html, admin-gear-kinds-options-dark.png and -light.png (the select expanded by
script to show every option), admin-gear-kinds-rejected-dark.png and -light.png (the inline after the
rejected post), admin-gear-kinds-errornote-dark.png and -light.png

ITEM 12. The Required content dashboard
Did: in a scratch database (the Postgres parity test database inside a rolled-back test, with no other
authored content), created one combat style with no skill, no hit stat and no weapon kind (named Bare Style) and
one active Tradition that teaches no style (named Lonely Tradition), then loaded the real Ops dashboard page
and the real required-content panel it loads (/admin/_ops/ and /admin/_ops/required-content/). The saved page
loads the panel by script, so for the picture I put the panel's real HTML into the page's own panel slot.
Expected: four tuning rows flagged: Skill on each combat style, Hit stat on each combat style, Weapon kinds on
each combat style, Each Tradition teaches a combat style, each naming the offender.
Saw: all four rows are in the Missing - Tuning table with the row class required-content-row--missing:
"Bare Style: 1 combat style(s) have no skill: their rolls add none."; "Bare Style: 1 combat style(s) have no hit
stat: a Strike uses the weapon's."; "Bare Style: 1 combat style(s) list no weapon kind: their skill never counts on
an attack."; "Lonely Tradition: 1 active Tradition(s) teach no combat style." Each label links to the admin
(CombatStyle or Tradition). The scratch database has no other content, so that table also lists many unrelated
rows; the four-row picture is cropped to the four rows.
Files: required-content-four-rows-dark.png and -light.png, required-content-tuning-heading-dark.png and
-light.png (the Missing - Tuning heading and header row, above the rows), required-content-fragment.html,
required-content-ops-page.html

Also seen: the inherited combat style journeys (ReadingTheDefenseRoll and TechniquesInStyle, 26 tests in the
run with the recorders) passed at c1a2a8730 on the Postgres database.
