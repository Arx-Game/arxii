# Review evidence

- Reviewed revision: b6a2a0e7a0977594982dec979a3cf2b9557100d6
- Reviewer: demo-fidelity-reviewer
- Reviewer verdict: PASS
- Application/build identity: Arx II Django admin served from the #5041 worktree at commit b6a2a0e7a0977594982dec979a3cf2b9557100d6, http://localhost:4001, isolated database rt_5041 (re-review after fixes to the 0ba866e findings)
- Environment: local dev server, staff superuser session cookie, Chromium via Playwright, SQLite-or-isolated dev database rt_5041 seeded with two example damage types and one seeded longsword template
- Viewports/themes: 1280x900 desktop viewport, light theme (full-page captures). Dark theme not rendered; the new pages add no theme-specific CSS and use the host admin stylesheets.
- Approved design: https://claude.ai/artifact/7WAQ187potcsgJaGjNYqe7 (published version 2, read in full from the local copy item-template-forms.html: Screens 1 to 7, the "Which page shows which option" matrix and the example-items table). Spec: issue 5041, Decisions 5 to 9 are owner rulings.
- Visual review: Completed. Rendered every new page and the all-kinds page in a real browser, read each screenshot with vision, and compared region by region against the demo screens. Also extracted the live DOM (fieldset titles, field labels, help lines, inline TOTAL_FORMS, gear archetype options, linked stylesheets) to confirm the screenshots.
- Visual verdict: PASS
- Screenshots: ![admin index Items module, implementer capture](.github/issue-evidence/5041/0-admin-index-items.png) ![weapon add](.github/issue-evidence/5041/r-1-weapon.png) ![armor add](.github/issue-evidence/5041/r-2-armor.png) ![shield add](.github/issue-evidence/5041/r-3-shield.png) ![clothing and jewelry add](.github/issue-evidence/5041/r-4-worn.png) ![all kinds add](.github/issue-evidence/5041/r-5-allkinds.png) ![weapon changelist after save, implementer capture](.github/issue-evidence/5041/6-weapon-changelist-after-save.png)
- Comparison notes: Every region the demo draws is present, in the demo's order, styled by the host admin (forms.css is linked on all five add pages, so aligned label columns, help lines, collapsed groups, inline tables and the submit row are drawn, not browser defaults). Both findings from the 0ba866e review are fixed: the shield page now shows a read-only "Gear archetype: Shield" row with no picker, and the four new pages sit directly after Item templates on the admin home in the demo's order. Accepted differences, none a defect: (a) the breadcrumb reads "Home > Arx II > ..." where the demo omits the app label; this is the host single-app admin label on every admin page and is unchanged by this work; (b) the demo's example numbers and names (4, 12.00, Example dagger) are placeholders, the build shows model defaults; (c) several model help lines carry issue references the demo's paraphrase omits, for example "(#2879)" and "(#5026)"; the demo states help text is the model's real text, and the text is pre-existing; (d) the live "Also protects against" list stacks its two real damage types vertically with the host related-widget add icon, where the demo draws three example boxes in a row; same widget as on the all-kinds page today; (e) the weapon, armor and clothing pickers open on "---------" with no default, which the spec requires. Not independently re-operated by this reviewer: the save writes. The implementer's capture of the saved dagger in the Weapon templates changelist was viewed and the stated seam tests cover value equality; those are outside the visual comparison.
- Tested interactions: Opened /admin/, then the add page of weapon, armor, shield, clothing and jewelry, and all-kinds item templates as a staff superuser. On each, read the kind picker options, fieldset titles, every field label and help line, every inline group's TOTAL_FORMS and its "Add another" link, the submit row buttons, the collapsed groups, and the linked stylesheet list. Viewed the implementer's capture of saving a throwable dagger through the weapon page and landing on the Weapon templates changelist with the success message, gear archetype filter and credit status filter. No server was started, stopped or restarted and no rows were added by this review.
- Fixture/live boundary: Live Django admin code at the reviewed commit against an isolated development database. The data is fixture-like (two example damage types, a seeded longsword, an RT2 Dagger and an RT Dagger saved by earlier operation runs); no production data was touched. The demo is a static mockup whose names and numbers are examples.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| S1-index | PASS | Admin home Items module lists Item templates, Weapon templates, Armor templates, Shield templates, Clothing and jewelry templates consecutively; see 0-admin-index-items.png and the DOM link order read from /admin/ | none needed |
| S2-weapon | PASS | r-1-weapon.png: six weapon kinds only, Weapon group, Physical properties, collapsed Resonance tie and Credit, three empty inlines | none needed |
| S3-armor | PASS | r-2-armor.png: four armor kinds only, soak and also-protects-against, four empty inlines including Garment mitigations | none needed |
| S4-shield | PASS | r-3-shield.png: read-only Gear archetype Shield, soak, also-protects-against, weapon class, damage, damage type, four empty inlines | Decision 6 |
| S5-worn | PASS | r-4-worn.png: Clothing and Jewelry only, supports open close, no combat stats, four empty inlines | Decision 5 |
| S6-allkinds | PASS | r-5-allkinds.png: every kind, Container and stack, Mechanics, Resonance tie, Cosmetics, Credit groups kept; all seven inlines TOTAL_FORMS 0 | Decision 9 |
| S7-saves | PASS | 6-weapon-changelist-after-save.png: saved dagger lists under Weapon templates with the success message and filters | none needed |
| CSS-reach | PASS | Each add page links base.css, forms.css, arx_admin.css and responsive.css; rendered result shows aligned label rows, header-bar groups and the submit row in the screenshots | none needed |
| Copy | PASS | Help lines for weapon class, base weapon damage, thrown, max durability, soak, also-protects-against, supports open close are present on the expected pages | none needed |
| Unbuilt-affordances | PASS | No demo affordance is unbuilt; the demo's design notes (dashed boxes) are explicitly not admin content | none needed |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Screen 1 Items module heading | A module headed Items | MATCH | 0-admin-index-items.png |
| Screen 1 Weapon templates link | Listed under Items | MATCH | 0-admin-index-items.png |
| Screen 1 Armor templates link | Listed under Items | MATCH | 0-admin-index-items.png |
| Screen 1 Shield templates link | Listed under Items | MATCH | 0-admin-index-items.png |
| Screen 1 Clothing and jewelry templates link | Listed under Items | MATCH | 0-admin-index-items.png |
| Screen 1 Item templates link | Still listed, the four new pages directly after it in demo order | MATCH | 0-admin-index-items.png |
| Screen 2 title and breadcrumb | Add weapon template under Weapon templates (host adds the "Arx II" app crumb, accepted) | MATCH | r-1-weapon.png |
| Screen 2 top group | Name required, Description, Is active ticked | MATCH | r-1-weapon.png |
| Screen 2 Weapon group heading | Group titled Weapon | MATCH | r-1-weapon.png |
| Screen 2 Gear archetype | Required picker offering only One-Handed Melee, Two-Handed Melee, Ranged, Thrown, Lance, Unarmed | MATCH | r-1-weapon.png |
| Screen 2 Weapon class | Select with weighted blend help line | MATCH | r-1-weapon.png |
| Screen 2 Base weapon damage | Number field with weapon archetypes only help | MATCH | r-1-weapon.png |
| Screen 2 Weapon damage type | Lookup field | MATCH | r-1-weapon.png |
| Screen 2 Can also be thrown | Checkbox labelled Can also be thrown with the throw help text | MATCH | r-1-weapon.png |
| Screen 2 Physical properties | Weight, Size, Value, Max durability with help, Minimum quality tier, Image | MATCH | r-1-weapon.png |
| Screen 2 Resonance tie | Collapsed group | MATCH | r-1-weapon.png |
| Screen 2 Credit | Collapsed group | MATCH | r-1-weapon.png |
| Screen 2 Template slots | Empty inline with Add another Template slot | MATCH | r-1-weapon.png |
| Screen 2 Check Modifiers | Empty inline with Add another Check Modifier | MATCH | r-1-weapon.png |
| Screen 2 Default Properties | Empty inline with Add another Default Property | MATCH | r-1-weapon.png |
| Screen 2 no armor, container or consumable fields | None shown | MATCH | r-1-weapon.png |
| Screen 2 submit row | Save and add another, Save and continue editing, Save | MATCH | r-1-weapon.png |
| Screen 3 title and top group | Add armor template; Name, Description, Is active | MATCH | r-2-armor.png |
| Screen 3 Armor group and Gear archetype | Picker offering only Light, Medium, Heavy Armor and Robe | MATCH | r-2-armor.png |
| Screen 3 Base armor soak | Number field with armor archetypes only help | MATCH | r-2-armor.png |
| Screen 3 Also protects against | Checkbox list of damage types with the physical-blows help line (stacked with host add icon, accepted) | MATCH | r-2-armor.png |
| Screen 3 Physical properties | Six rows as on the weapon page | MATCH | r-2-armor.png |
| Screen 3 Resonance tie and Credit | Both collapsed | MATCH | r-2-armor.png |
| Screen 3 inlines | Template slots, Garment mitigations, Check Modifiers, Default Properties, all empty | MATCH | r-2-armor.png |
| Screen 3 no weapon fields | None shown | MATCH | r-2-armor.png |
| Screen 3 submit row | Three buttons | MATCH | r-2-armor.png |
| Screen 4 title and top group | Add shield template; Name, Description, Is active | MATCH | r-3-shield.png |
| Screen 4 Gear archetype | Read-only text Shield, no picker (fixed in b6a2a0e) | MATCH | r-3-shield.png |
| Screen 4 Base armor soak and Also protects against | Both present with help lines | MATCH | r-3-shield.png |
| Screen 4 Weapon class, Base weapon damage, Weapon damage type | All three present with help lines | MATCH | r-3-shield.png |
| Screen 4 Physical properties | Six rows | MATCH | r-3-shield.png |
| Screen 4 Resonance tie and Credit | Both collapsed | MATCH | r-3-shield.png |
| Screen 4 inlines | Template slots, Garment mitigations, Check Modifiers, Default Properties, all empty | MATCH | r-3-shield.png |
| Screen 4 no Can also be thrown | Absent | MATCH | r-3-shield.png |
| Screen 4 submit row | Three buttons | MATCH | r-3-shield.png |
| Screen 5 title and top group | Add clothing and jewelry template; Name, Description, Is active | MATCH | r-4-worn.png |
| Screen 5 group heading | Clothing or jewelry | MATCH | r-4-worn.png |
| Screen 5 Gear archetype | Picker offering only Clothing and Jewelry | MATCH | r-4-worn.png |
| Screen 5 Supports open close | Checkbox with coats, bags, lockets help | MATCH | r-4-worn.png |
| Screen 5 Physical properties | Six rows | MATCH | r-4-worn.png |
| Screen 5 Resonance tie and Credit | Both collapsed | MATCH | r-4-worn.png |
| Screen 5 inlines | Template slots, Garment mitigations, Check Modifiers, Default Properties, all empty | MATCH | r-4-worn.png |
| Screen 5 no combat stats | None shown | MATCH | r-4-worn.png |
| Screen 5 submit row | Three buttons | MATCH | r-4-worn.png |
| Screen 6 all-kinds page | Same groups and fields as today: Physical properties with every kind picker, weapon, armor, Container and stack, Mechanics, Resonance tie, Cosmetics, Credit | MATCH | r-5-allkinds.png |
| Screen 6 seven inlines | Template slots, Template interactions, Garment mitigations, Appearance Effects, Disguise Kit Effects, Check Modifiers, Default Properties, all empty with Add another links | MATCH | r-5-allkinds.png |
| Screen 7 what saving writes | One item template row through the weapon page, listed on its changelist | MATCH | 6-weapon-changelist-after-save.png |
| Option matrix, weapon column | Weapon fields and thrown yes; armor, open close, container, consumable, interactions no | MATCH | r-1-weapon.png |
| Option matrix, armor column | Soak and also protects yes, weapon fields no, garment mitigations yes | MATCH | r-2-armor.png |
| Option matrix, shield column | Soak, protects, weapon class, damage, damage type yes; thrown no | MATCH | r-3-shield.png |
| Option matrix, clothing column | Open close yes; combat stats no; garment mitigations yes | MATCH | r-4-worn.png |
| Option matrix, resonance closed on four pages | Resonance tie collapsed on each of the four new pages | MATCH | r-2-armor.png |

## Unresolved findings

None
