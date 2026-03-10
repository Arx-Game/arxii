# RP Interaction & Scenes

**Status:** in-progress
**Depends on:** Checks, Relationships, Magic (aura farming)

## Overview
The core RP experience — how players interact in scenes. Arx II replaces arcane telnet commands with a modern web interface that lets players attach mechanical actions to their poses, react to each other's writing, and build skills and relationships during what would otherwise be trivial social scenes.

## Key Design Points
- **Rich text editor:** Modern compose experience replacing telnet command-line input. Lower barrier to entry for new players unfamiliar with MUSH conventions
- **Action-attached poses:** Players can embed mechanical actions directly in their writing — flirtation checks, pickpocketing attempts, dice rolls, arm wrestling, throwing objects. Seamlessly integrated into the narrative flow rather than jarring separate commands
- **Scene engagement mechanics:** Reactions/emoticons on poses, liking poses, pose-of-the-scene awards. Younger players used to social media can engage naturally
- **Passive advancement:** Social scenes mechanically advance characters — skill development, relationship building, magical discoveries can all happen during bar scenes and balls
- **Aura farming:** A character's resonance feeds off how they're perceived. Writing a dramatic entrance at a ball literally increases magical power. Making the social game mechanically meaningful
- **Scene modes:** Poses, says, whispers — different communication modes within a scene, including private exchanges
- **Persona/disguise system:** Characters can appear under alternate identities during scenes
- **Scene recording:** All scenes are recorded for continuity, story tracking, and reference
- **Dice rolling integration:** Checks and attempts woven into scene flow without disrupting narrative pacing

## What Exists
- **Models:** Scene (session recording with location, status, participants), SceneParticipation (character tracking), Persona (identity management for disguises), SceneMessage (dialogue/actions with context and mode), SceneMessageReaction (reactions to messages)
- **APIs:** Full viewsets for scenes, messages, participation
- **Frontend:** Scene components and pages exist in frontend/src/scenes/
- **Commands:** Pose/say/whisper commands exist
- **Tests:** Comprehensive permission and view tests

## What's Needed for MVP
- Rich text editor for pose composition (replacing plain text input)
- Action-attached poses — UI for embedding checks/actions within a pose
- Pose reactions and engagement — likes, emoticons, awards integration
- Aura farming mechanics — how scene perception feeds into resonance
- Skill development during scenes — passive advancement from scene participation. Certain scene checks award development points and prevent rust for that skill that week (TODO: define which check types qualify)
- Relationship development triggers — mechanical relationship changes from scene interactions
- Magical discovery during scenes — unpredictable magical moments during RP
- Scene-based XP rewards — earning XP for participation and quality
- Dice roll integration in scene UI — seamless check/attempt display within narrative flow
- Scene scheduling and discovery — finding active scenes, joining easily

## Notes
