# Episodes/Seasons to Stories Migration

This document outlines the fundamental shift from Arx I's Episodes/Seasons system to Arx II's Story-focused approach.

## Arx I System: Episodes and Seasons

In Arx I, the game was structured around:

### Episodes
- Brief narrative containers that served as dividers for chapters
- Associated with specific actions and plot updates
- Used primarily for administrative organization rather than player-facing content
- Players were limited to one action per episode
- Episodes were created automatically when crisis updates were published

### Seasons
- Higher-level organizational structure stored as a simple integer field on Story objects
- Used to group multiple stories together chronologically
- Limited storytelling utility beyond basic categorization

### Plot System Integration
- **Crises**: Large-scale events affecting organizations or the entire game world
- **GM Plots**: Staff-run stories for subsets of players
- **Player-Run Plots**: Player-initiated stories with limited scope
- **Personal Stories**: Individual character arcs
- Actions were tied to specific episodes for tracking and limiting purposes

## Arx II System: Stories as Primary Narrative Structure

### Core Philosophy Shift
Arx II places **Stories** at the center of the narrative experience, moving away from administrative episodes toward meaningful, ongoing narratives.

### Story System Features

#### Story Ownership and Management
- **Player Ownership**: Players can own and control their stories
- **GM Assignment**: Story owners can assign GMs or seek them out
- **Collaborative GMing**: Multiple GMs can collaborate on a single story
- **Access Control**: Story owners control who can participate or GM

#### GM Trust and Authority System
- **Trust Levels**: GMs gain trust through successful story facilitation
- **Progressive Authority**: Higher trust levels unlock greater GM capabilities
- **Player Feedback**: Trust is built through positive player experiences
- **Accountability**: System tracks GM performance and player satisfaction

#### Story Discovery and Participation
- **Hooks System**: In-game hooks allow players to discover and join stories
- **Active Recruitment**: Players can seek out GMs for their personal stories
- **Flexible Participation**: Stories can be private, semi-private, or public
- **Dynamic Entry**: Players can join ongoing stories through hooks

#### Reward Structure
- **Development Points**: Stories reward character development and relationship building
- **Trait Advancement**: Development points used for raising skills, stats, and relationships
- **XP from Roleplay**: Traditional XP comes from roleplay rewards and achievements
- **Story Completion**: Bonus rewards for completing meaningful story arcs

### Story Types and Scale

#### The Overarching Story
- **Gamerunner-Led**: The primary story involving all players
- **World-Shaping**: Major events that affect the entire game world
- **Mandatory Participation**: All players are involved to some degree
- **Epic Scale**: Long-running narrative spanning multiple real-world years

#### Personal Stories
- **Character-Focused**: Individual character development and goals
- **GM Partnership**: Players work with trusted GMs to tell their stories
- **Flexible Scope**: Can be intimate personal moments or character-changing events
- **Player Agency**: High degree of player control over narrative direction

#### Group Stories
- **Multiple Characters**: Stories involving 2-10 characters typically
- **Relationship Building**: Focus on character interactions and development
- **Collaborative**: Shared narrative control between players and GMs
- **Medium Duration**: Usually spanning weeks to months

#### Private Stories
- **Exclusive Access**: Limited to invited participants only
- **Sensitive Content**: Stories dealing with personal or controversial themes
- **Trust-Based**: Requires established relationships between participants
- **Protected Space**: Safe environment for exploring difficult topics

### Integration with Scenes System

Stories provide the narrative framework within which scenes occur:

- **Scene Context**: Every scene should ideally connect to an ongoing story
- **Progression Tracking**: Scenes advance story beats and character development
- **Relationship Building**: Scenes within stories build meaningful character relationships
- **Development Rewards**: Story-contextualized scenes provide development points
- **Narrative Continuity**: Scenes create the moment-to-moment narrative within larger stories

## Key Differences from Arx I

### Narrative Focus vs. Administrative Focus
- **Arx I**: Episodes were primarily administrative tools for limiting actions
- **Arx II**: Stories are narrative containers that drive meaningful roleplay

### Player Agency
- **Arx I**: Players participated in staff-created plots with limited control
- **Arx II**: Players can own, control, and direct their own stories

### GM Development
- **Arx I**: GMing was primarily a staff responsibility
- **Arx II**: Player-GMs are developed through a trust system with progressive authority

### Reward Philosophy
- **Arx I**: XP and advancement tied to action submissions and plot participation
- **Arx II**: Development points from story participation, XP from roleplay achievements

### Scale and Accessibility
- **Arx I**: Heavy focus on large-scale crises and org-level politics
- **Arx II**: Emphasis on personal stories and character relationships alongside epic narratives

### Participation Model
- **Arx I**: Invitation-based plot participation with formal status tracking
- **Arx II**: Hook-based discovery with flexible, organic participation

## Implementation Considerations

### Database Design
- Stories as the primary organizational entity, not episodes
- GM trust tracking and authority levels
- Story ownership and participant management
- Hook systems for story discovery
- Development point allocation and tracking

### Scene Integration
- All scenes should reference associated stories where applicable
- Story progression tracking through scene participation
- Development point rewards calculated per story involvement
- Cross-story scene support for characters in multiple narratives

### Migration Strategy
- We're starting fresh, like all other Arx I to II migrations. Designs, not data.

This shift represents a fundamental change in how narrative content is created, managed, and experienced in Arx II, prioritizing player agency and meaningful storytelling over administrative convenience.
