# Achievements & Discoveries

**Status:** not-started
**Depends on:** All systems (achievements track actions across every domain)

## Overview
A meta-engagement layer inspired by Everquest 2's discovery system and Steam achievements. Characters earn achievements for milestones across every system, with first-to-achieve "discoveries" that make early accomplishments feel special. Achievements add flavor, drive exploration, and some gate progression requirements.

## Key Design Points
- **Hidden achievements:** Many achievements are hidden until earned, creating surprise and delight when triggered. Players discovering an "Enemies with Benefits" achievement for transitioning a rivalry into romance
- **Discovery system:** First-to-achieve tracking with IC/OOC timestamps. Being the first person in the game to accomplish something gets a special "discovered by" banner — making it feel uniquely special
- **Broad stat tracking:** Combat kills, thefts, seductions, missions completed, relationship milestones, spells cast, items crafted, scenes participated in — extensive tracking across all systems
- **Achievement chains:** Achievements unlock further achievements with escalating rewards. Early achievements are easy; later ones in the chain require serious dedication
- **Mechanical bonuses:** Achievements aren't just bragging rights — they come with bonuses, unlocks, and rewards
- **Path progression gating:** Some achievements may be requirements for higher Path levels, ensuring characters engage broadly with the game rather than min-maxing one system
- **Fun and flavor:** Achievements like "Vampiric Casanova" (seduced X people as a vampire) or "Underdog Victory" (won a fight-to-death as the underdog) add personality and humor to the game
- **Encourages exploration:** Hidden achievements drive players to try unusual things, explore unexpected corners of the world, and engage with systems they might otherwise skip

## What Exists
- **Nothing.** No achievement models, stat tracking, or discovery system exists
- **Progression app** has some reward/unlock models that could potentially connect

## What's Needed for MVP
- Achievement definition model — name, description, requirements, rewards, hidden flag
- Discovery tracking — first-to-achieve with timestamps and character attribution
- Stat tracking system — counters for trackable actions across all systems (kills, thefts, crafts, etc.)
- Achievement chain model — prerequisite achievements, escalating tiers
- Achievement trigger engine — evaluating stat thresholds and conditions to grant achievements
- Reward distribution — bonuses, unlocks, items, titles awarded on achievement
- Integration hooks — every major system needs to fire events that the achievement tracker can listen to
- Achievement UI — notification popups, achievement browser, discovery hall of fame
- Path progression integration — linking specific achievements as Path step requirements

## Notes
