Answers to the open evidence-challenge claims, issue 4884 (PR 4890), re-recorded at d0ddfae4f

Reviewed commit for every file listed here: d0ddfae4f13310a1a75966c6b25b1f5b9703ace9 (d0ddfae4f),
read back with git rev-parse HEAD inside the throwaway worktree. Each JSON file carries it as
"reviewed_commit" and each saved HTML file starts with a comment naming it; the PNGs are named for their
scenario and this index names the commit for them. The files from the c1a2a8730 recording are gone and
replaced.

Method (real runs through the code, not mocks of it). I made a throwaway detached worktree at that commit with
its own Postgres database (built from that commit's models) and removed both afterwards. No source was edited.
- Strike: the combat_strike web action through dispatch_player_action, resolved by resolve_round.
- Defense: a real NPC Blade blow in resolve_round; the PC's real Parry check.
- Readbacks: the REST endpoints /api/checks/consequence-outcomes/ and /api/interactions/ as Mira's account,
  and the consequence-outcomes endpoint again as Wren, a second scene participant who is a bystander.
- Renders: the real CombatTurnPanel in headless Chromium, fed those recorded payloads.
- Admin pages: the real Django admin through the test client, styled with the admin's own CSS, with the admin's
  JavaScript stripped from the copy that was rendered.
Forced: each roll's outcome name (Strike hit and damage Success, defense Partial Success). Test data: factory
style, character, weapon and Blade; names like trait_15 or CheckType6 in the technique files are factory names.
Fixture round: Mira has The Daring Dance (Magic skill rating 20, hit stat Strength, evasion defense, armor share
5 of 10, works with the vow Quicksilver), Melee Combat 25, Dodge 15, a one-handed "Steading longsword" and light
armor, and 100 health. The Blade strikes her once in the round. What the style lists decides the scenario:
off-style lists two-handed melee and heavy armor; listed and vow list one-handed melee and light armor.
How to rerun: record-answers.py.txt (the recorder, a throwaway test), harness-CombatTurnPanel.tsx.txt and
shoot-final.mjs.txt (the render harness and script).

ITEM A. The off-style round (Strike off-style, defense in off-style armor, whole round, bystander)
Head: d0ddfae4f.
Did: Mira Struck the Blade with the one-handed sword while her style lists only two-handed melee and heavy
armor; the Blade then struck her in her light armor; resolved the round; read back as Mira and as Wren.
Expected (spec and the 2026-11-01 rulings): on the Strike the style skill lapses with the weapon as the reason, the
style's hit stat still applies; on the defense the style skill lapses with the armor as the reason and the style's
armor share still counts (half of 4 soak, 8 damage of a 10 blow); the defender's Last Outcome shows the whole
newest round (the defense card and the Strike's hit and damage cards together); a bystander sees no breakdown, no
defense row, and no modifiers.
Saw: Strike hit roll kwargs: extra_traits empty, stat_override strength. Defender readback, three cards: "Defense
against Blade": Dodge 15 "defense skill"; The Daring Dance lapsed true "light armor is not this style's"; "Armor, 5 of
10 / the style's armor share" counted; result "Partial Success, 8 damage". "Hit roll against Blade's defense":
Melee Combat 25 "strike skill for one-handed melee"; Strength "the style's hit stat" (not lapsed); The Daring Dance
lapsed true "one-handed weapons are not this style's"; result "Hit, fair". "Damage roll": Steading longsword, Melee
Combat 25, "6 damage". Mira's health 100 before, 92 after. Bystander readback: three rows with roll_breakdown null
and modifiers empty; the defense row's summary is empty, the hit row reads "Hit, fair" and the damage row "6
damage" (damage dealt to the opponent, kept by design). The render of the defender shows three cards with two
struck labels (checked in the page), no horizontal overflow at 1280 or 390 wide; the bystander render shows only
"Hit, fair" and "6 damage".
Files: round-offstyle.json (full recording), readback-offstyle.json (excerpt: kwargs, health, breakdowns, bystander
rows), lastoutcome-offstyle-defender-{desktop,phone}-{dark,light}.png, panel-offstyle-{desktop,phone}-{dark,light}.png
(the whole turn panel with Last Outcome at the bottom), lastoutcome-offstyle-bystander-{desktop,phone}-{dark,light}.png

ITEM 2. A Strike with a LISTED weapon
Head: d0ddfae4f.
Did: Mira Struck with the listed one-handed sword, style listing one-handed melee and light armor; resolved the round.
Expected: the hit roll adds the style skill (weight 1) and uses the style's hit stat; the hit card shows the style skill
row with its rating and the hit stat row.
Saw: hit roll kwargs extra_traits = The Daring Dance weight 1, stat_override = strength. Readback hit card: Melee
Combat 25 "strike skill for one-handed melee"; Strength "the style's hit stat"; The Daring Dance 20 "style skill" (lapsed
false); "Hit, fair". The render shows the style row with 20, unstruck (0 struck labels in the page).
Files: round-listed.json, readback-listed.json, lastoutcome-listed-defender-{desktop,phone}-{dark,light}.png

ITEM 5. A defense roll in LISTED armor
Head: d0ddfae4f.
Did: same round; the Blade struck Mira in the light armor the style lists.
Expected: the defense card shows the style skill with its rating, not struck, and the armor share.
Saw: readback "Defense against Blade": Dodge 15; The Daring Dance 20 "style skill" (lapsed false); "Armor, 5 of 10 / the
style's armor share"; "Partial Success, 8 damage"; health 100 to 92. The render shows the style row unstruck.
Files: the same files as item 2 (the defense card is the first card).

ITEM 6a. A held vow NOT on the style's list lapses the Strike and the defense roll, each naming the vow
Head: d0ddfae4f.
Did: same style, which works only with the vow Quicksilver; Mira swore the vow Bulwark; same Strike and blow.
Expected: the style skill stops counting on both rolls with the vow named as the reason; the hit stat and the armor
share still apply.
Saw: Strike roll kwargs extra_traits empty, stat_override strength. Readback hit card: The Daring Dance lapsed true,
"Bulwark is not this style's vow"; Strength row kept. Readback defense card: The Daring Dance lapsed true, "Bulwark
is not this style's vow"; "Armor, 5 of 10" counted; 8 damage. The render shows both style rows struck.
Files: round-vow.json, readback-vow.json, lastoutcome-vow-defender-{desktop,phone}-{dark,light}.png

ITEM 6b. A technique hit roll
Head: d0ddfae4f.
Did: Ysmay (a Path with a technique skill) declared a technique through dispatch_player_action holding a one-handed
weapon the style lists (style lists one-handed melee, hit stat Strength); resolve_round ran. Techniques record no
breakdown row, so this was captured from the real roll call: a spy wrapped around the perform_check that
resolve_round calls kept the kwargs it received and then called the real function.
Expected: the style skill is added to the extra traits next to the Path's technique skill; the style's hit stat is not
imposed on a technique.
Saw: extra_traits received = the Path's technique skill (1.00) and The Daring Dance (1); stat_override received =
agility, the held weapon's own stat; the style's strength was not used.
File: technique-b-listed-weapon.json

ITEM 6c. A weaponless cast keeps the style skill
Head: d0ddfae4f.
Did: Ysmay cast with no weapon in hand; the style lists only two-handed melee. Same spy.
Expected: nothing to test against, so the style skill still counts, and the technique rolls its own check's stat.
Saw: extra_traits received = the Path's technique skill and The Daring Dance weight 1; stat_override received = null.
File: technique-c-weaponless.json

ITEM 9. The scene feed after an NPC blow
Head: d0ddfae4f.
Did: in the listed round, read GET /api/interactions/?scene=SCENE_ID as Mira after resolve_round, and spied the
interaction send seam (interaction_services._send_to_objects) while the round resolved, to catch the live frame.
Expected: the Narrator ACTION row "Blade strike at Mira" (threat name, "at", target) is in the feed and was also pushed
live.
Saw: feed row id 1: persona Narrator, mode action, content "Blade strike at Mira", target persona Mira's. The send
seam received the same row (id 1, same content and mode) addressed to the room contents Mira and Blade, before the
other three rows (Narrator outcome "Blade's Blade strike strikes Mira for 8 damage.", Mira's action "Strike at
Blade", Narrator outcome "Mira strikes Blade with a Steading longsword. A fair hit: 6 damage."). The frame is
captured where the payload is handed to each room object's msg(), not on a browser websocket; I did not render the
scene feed component.
Files: feed-narrator-action-row.json (row, frame, both orders); full data in round-listed.json under feed_readback
and live_frames_captured_at_the_send_seam.

ITEM 11. The Gear kinds choice list and a rejected save of a kind that is neither weapon nor armor
Head: d0ddfae4f.
Did: opened a style's change page as a superuser and read the options of the Gear kinds select (the saved row and the
Add-another template row); then posted the page's own form back unchanged plus one new Gear kinds row of kind
"jewelry" (Save and continue editing).
Expected: only weapon and armor kinds are offered, and any other kind is refused with a form error and not saved.
Saw: offered, in order: Light Armor, Medium Armor, Heavy Armor, Robe, One-Handed Melee, Two-Handed Melee, Ranged,
Thrown, Shield, Lance, Unarmed (Jewelry, Clothing and Other are absent). The POST answered 200 and showed the form
again. The error text was read out of the response HTML and written to gear-kinds-rejected-post.json: error note
"Please correct the error below."; field error on gear-1-gear_archetype: "Select a valid choice. jewelry is not one of
the available choices." Rows before 1, after 1: nothing saved. That is the only error on the page.
Files: gear-kinds-rejected-post.json (the quoted errors), gear-kinds-rejected-post.html (the response, cut to the error
note and the Gear kinds inline, about 6KB, containing the quoted error), gear-kinds-offered-options.json,
gear-kinds-change-page.html (the inline as served, cut), admin-gear-kinds-options-{dark,light}.png (select expanded
by script to show every option), admin-gear-kinds-rejected-{dark,light}.png

ITEM 12. The Required content dashboard
Head: d0ddfae4f.
Did: in a scratch database (the Postgres test database inside a rolled-back test, no other authored content) created
one combat style with no skill, no hit stat and no weapon kind ("Bare Style") and one active Tradition that teaches no
style ("Lonely Tradition"); requested the real endpoint /admin/_ops/required-content/ (the panel the Ops page loads)
and /admin/_ops/ as a superuser; both answered 200. Read the four rows out of the endpoint's HTML into
required-content-rows.json.
Expected: four tuning rows flagged: Skill on each combat style, Hit stat on each combat style, Weapon kinds on each
combat style, Each Tradition teaches a combat style, each naming the offender.
Saw: all four are in the "Missing - Tuning" table, class required-content-row--missing, each label linking to the admin
list (CombatStyle or Tradition):
 Skill on each combat style: "Bare Style 1 combat style(s) have no skill: their rolls add none."
 Hit stat on each combat style: "Bare Style 1 combat style(s) have no hit stat: a Strike uses the weapon's."
 Weapon kinds on each combat style: "Bare Style 1 combat style(s) list no weapon kind: their skill never counts on an
 attack."
 Each Tradition teaches a combat style: "Lonely Tradition 1 active Tradition(s) teach no combat style."
The screenshots are a render of that saved fragment HTML placed into the Ops page's own panel slot (the Ops page
loads the panel by script, which I stripped); they are not a capture of the live page. The scratch database has no
other content, so the same table lists many unrelated rows; the four-row picture is cropped to the four rows.
Files: required-content-rows.json (the strings, read from the endpoint), required-content-fragment.html (the endpoint's
full response), required-content-ops-page.html, required-content-four-rows-{dark,light}.png,
required-content-tuning-heading-{dark,light}.png
