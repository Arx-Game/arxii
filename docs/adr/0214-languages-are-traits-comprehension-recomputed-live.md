# Languages ride the Trait/DevelopmentPoints substrate; comprehension recomputes live per viewer

Language fluency (#2993) is not a dedicated `CharacterLanguage` progression model — a `Language`
catalog row links to a `TraitType.LANGUAGE` `Trait`, and per-character fluency is an ordinary 1-100
`CharacterTraitValue` trained through the same `DevelopmentPoints`/`CharacterTraitChange` machinery
every other trait uses (`TrainLanguageAction`'s weekly teacher/self-study sessions, rust exemption
for the type). Comprehension — how garbled a listener sees another character's speech — is computed
live at every render (telnet delivery, WS push, and scene-log reads) from `min(speaker_band,
listener_band)` and a deterministic word-survival garble (`garble_text`, seeded on
`language_id:text`), never persisted or snapshotted onto the `Interaction` row. Rejected: a dedicated
`CharacterLanguage` model tracking fluency/progression outside Trait/DevelopmentPoints, which would
duplicate the whole leveling/training stack one system over for no mechanical difference; and an
ADR-0170-style pose-time snapshot (materializing each viewer's resolved comprehension as receiver
rows at write time) — ADR-0170 snapshots because *retroactive* perception there would be a leak (a
bystander who later gains a detection capability must not "see" a concealed cast their character
missed), but for languages the opposite holds: a character who learns a tongue after the fact
*should* be able to reread old scene logs in the clear, and the seed's determinism is exactly what
makes that recompute stable and byte-identical across live delivery, WS push, and every later read.

**Amendment (#4090, 2026-10-03).** Comprehension is trained fluency plus the
`ConditionModifierEffect` bonuses an active condition carries toward the language trait's
`ModifierTarget` (`comprehension_value`; batched on the reread by
`condition_modifier_totals_by_sheet`), recomputed live like the rest of comprehension: while a
condition lasts, old lines in that tongue read clear on reread, and they garble again after it
ends. Any condition source counts (a technique's applied condition, a GM's catalog
application, anything else that applies a condition); `CharacterModifier` sources such as
distinctions and equipment do not. The bonus is listener-side only: speaking, the speaker's
own band, teaching and self-study stay on trained fluency. Rejected: a per-application
language column on `ConditionInstance` and a bespoke temporary-fluency model, both parallel to
the existing condition effect rows. Trained fluency's weekly rates are tuned on
`LanguageTrainingConfig`, and language training parks one rating below an authored
`TraitRatingUnlock` until an XP breakthrough (`purchase_language_breakthrough`).

> Status: accepted · Source: #2993
