# Character Creation & Identity

**Status:** skeleton
**Depends on:** Magic, Traits, Skills, Distinctions, Species, Paths

## Overview
The 11-stage character creation flow that takes a player from concept to approved character. CG is the first experience every player has with the game, so it must be polished, informative, and exciting — setting the tone for everything that follows.

## Key Design Points
- 11 stages: Origin, Heritage, Lineage, Attributes, Skills, Distinctions, Path, Magic, Appearance, Identity, Review
- Draft system allows saving and resuming in-progress characters
- Application review workflow with staff conversation threads
- Admin-editable CG copy text (CGExplanation key-value system) so lore text can be updated without code changes
- Tradition templates reduce choice paralysis for new players by pre-filling magic selections
- Tarot card naming ritual for familyless characters (78-card deck with surname derivation)
- Points budget system configurable via admin

## What Exists
- **Models:** Full stage models, CharacterDraft with stage tracking, DraftApplication with review workflow, CGExplanation KV store, CGPointBudget, BeginningTradition templates
- **APIs:** Complete viewsets and serializers for all stages
- **Frontend:** Full React components for all 11 stages — OriginStage, HeritageStage, LineageStage, DistinctionsStage, PathStage, AttributesStage, MagicStage, AppearanceStage, IdentityStage, FinalTouchesStage, ReviewStage. Gift/Technique builders, Anima Ritual forms, Motif designers, CG Points widget, Species cards, Tarot selection
- **Tests:** Comprehensive coverage of stages, serializers, services, application workflow

## What's Needed for MVP
- Email verification and approval flow needs testing/completion
- Hundreds of distinctions still need to be authored as game content
- Lore text for all CG stages needs to be written and entered via CGExplanation
- Roster character system integration (characters that change players need strong records)
- Polish pass on UX — the skeleton works but the experience needs to feel exciting and informative

## Notes
