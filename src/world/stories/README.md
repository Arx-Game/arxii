# Stories System

The Stories system is one of the core gameplay mechanics in Arx II, serving as the primary way players
engage with the game world through narrative-driven content. It combines elements from traditional RPG
missions/quests with collaborative storytelling and player-driven narrative creation.

## Core Philosophy

Stories in Arx II are more than just quests or missions - they are the fundamental building blocks of
how players experience and shape the game world. Rather than being separate side content, stories are
integral to character development, world progression, and player engagement.

### Key Principles

1. **Player Agency**: Players own their stories and have control over their narrative direction
2. **Collaborative Storytelling**: Multiple players and GMs work together to create compelling narratives
3. **Trust-Based Participation**: A trust system ensures players can handle sensitive content appropriately
4. **Narrative Structure**: Stories follow proven narrative structures with clear consequences and connections
5. **Quality Over Quantity**: Better to have fewer, high-quality stories than many shallow ones

## System Overview

### Story Lifecycle

Stories progress through several stages:

1. **Creation**: A player creates a story concept, either personal or group-focused
2. **GM Assignment**: A GM is found to run the story (players cannot GM their own stories)
3. **Player Recruitment**: Other players apply to participate based on trust levels and story requirements
4. **Active Play**: The story is run through chapters and episodes with connected scenes
5. **Completion**: The story concludes with narrative resolution and consequence tracking

### Story Types

#### Personal Stories
Every character has a personal story that represents their individual character arc and development. These stories:
- Are owned by the character's player
- Focus on the character's personal goals, growth, and challenges
- Help characters engage with the larger game world
- Require a GM to run but are fundamentally about the individual character

#### Group Stories
Collaborative stories involving multiple characters working together:
- Can be owned by one or more players
- May have public or private/invite-only participation
- Can range from small group adventures to large-scale world events
- Require active GMs to run and coordinate

## Trust and Safety System

### Trust Levels
Players earn trust ratings (0-4) for different content elements and GM abilities:

- **Untrusted (0)**: Cannot participate in content requiring this element
- **Basic (1)**: Can handle simple scenarios with this element
- **Intermediate (2)**: Comfortable with moderate complexity
- **Advanced (3)**: Can handle complex and nuanced scenarios
- **Expert (4)**: Trusted to handle the most challenging content

### Content Elements
Stories can contain elements that require trust to participate in:

- **Antagonism**: Playing against other characters in meaningful ways
- **Mature Themes**: Adult content that requires sensitive handling
- **Romance**: Romantic storylines and relationships
- **Power Imbalances**: Whether a player can sensitively navigate a situation with power imbalances
- **Emotional Trauma**: Ability to handle potentially triggering elements sensitively
- **Dark Themes**: Darker content including horror, tragedy, or disturbing elements

### Trust Building
Trust is earned through:
- **Positive Feedback**: Other players rate performance in stories
- **GM Evaluation**: GMs provide feedback on player participation
- **Consistency**: Demonstrating reliability over time
- **Negative Impact**: Bad feedback hurts trust more than positive feedback helps it

## Roster Integration

The Stories system is deeply integrated with the roster application system:

### Character Availability Requirements
To apply for a character on the roster, a player must satisfy two trust requirements:

1. **Active Story Trust**: Must be trusted to play one active (GM'd) story for the character
2. **Critical Story Trust**: Must be trusted to play all stories where the character's participation is critical

This ensures that players taking on roster characters can handle the narrative responsibilities that come
with established characters who may be central to ongoing storylines.

### Story Ownership and Character Transfer
When a player applies for a roster character:
- They inherit any personal stories belonging to that character
- They must work with existing story owners to transition involvement
- Critical story participation cannot be abandoned without replacement

## GM System

### GM Characters
When players decide to become GMs, they receive:
- A special GM character typeclass added to their account
- Access to a unique CmdSet with GMing tools
- Frontend tools for story management and running scenes

### GM Trust and Experience
GMs are subject to their own trust system:
- **GM Trust Levels**: Similar to player trust but focused on running stories
- **GM Experience Points**: Earned for running stories and administrative tasks
- **Player Feedback**: Players provide feedback on GM performance
- **Administrative Tasks**: GMs earn XP for story-related admin work

### GM Limitations
- Players cannot GM their own stories (prevents conflicts of interest)
- Story owners can replace GMs if needed
- Inactive stories (without active GMs) cannot progress

## Narrative Structure

### Hierarchical Organization
Stories are organized in a three-tier hierarchy:

1. **Stories**: The overall narrative arc or campaign
2. **Chapters**: Major divisions within a story (like acts in a play)
3. **Episodes**: Smaller narrative units containing 2-5 scenes each

### Scene Integration
Episodes are composed of scenes from the scenes app:
- Each episode contains a small number of connected scenes
- Scenes represent individual "plot beats" or significant events
- A single scene can contribute to multiple stories simultaneously
- Scene connections within episodes follow narrative logic

### "But and Therefore" Rule
The system encourages strong narrative connections using the "but and therefore" principle:

#### Scene Level
Within episodes, scenes should connect via:
- **"Therefore"**: Logical consequences (Scene A leads to Scene B because...)
- **"But"**: Complications or obstacles (Scene A should lead to X, but Scene B happens instead)
- **Avoid "And Then"**: Disconnected events that don't build narrative momentum

#### Episode Level  
Episodes within chapters should similarly connect with clear causal relationships showing how the
story progresses logically from one episode to the next.

### Consequence Tracking
The system tracks narrative consequences at multiple levels:
- **Scene Consequences**: What changed as a result of this scene
- **Episode Consequences**: How this episode affects future episodes
- **Chapter Consequences**: Major story developments that impact the overall narrative

## Experience Points vs Trust System

The Stories system integrates with two separate progression mechanisms:

### Experience Points (handled by PlayerData/Progression app)
Players earn XP that is stored on PlayerData and spent on character unlocks:
- **Story Participation**: Players earn XP for active participation in stories
- **GM Activities**: GMs earn XP for running stories, planning, and administrative tasks
- **Story Support**: XP for feedback, summaries, and story maintenance tasks
- **Character Progression**: XP is spent on unlocks for any characters under the player's account

### Trust System (Stories-specific authorization)
Trust is a separate authorization system, orthogonal to XP:
- **Content Authorization**: Determines what content elements a player can handle
- **GM Authority**: High GM trust grants deeper access to metaplot and authority
- **Safety Mechanism**: Prevents exposure to unwanted or inappropriate content
- **Feedback-Based**: Built through peer review, with negative feedback having more impact

## Technical Implementation

### Database Structure
The system uses several key models:

- **Story**: Core story information, ownership, trust requirements
- **StoryParticipation**: Links characters to stories with participation levels
- **Chapter**: Major story divisions
- **Episode**: Smaller narrative units
- **EpisodeScene**: Links scenes to episodes with connection tracking
- **PlayerTrust**: Trust levels for content elements and GM abilities
- **StoryFeedback**: Player feedback for trust building

### Trust System Implementation
Trust levels are stored as integer values (0-4) for each content element:
- Calculated based on positive/negative feedback ratios
- Negative feedback has more impact than positive feedback
- Trust requirements can be overridden by story owners
- Trust levels determine story accessibility

### Integration Points
The Stories system integrates with:
- **Roster App**: Character availability requirements
- **Scenes App**: Episode scene connections
- **Accounts**: Player trust profiles and GM characters
- **Objects**: Character participation tracking

## User Experience Goals

### For Players
- **Clear Progression**: Understand how to earn trust and access better stories
- **Meaningful Choice**: Stories that matter to character development and world progression
- **Safety**: Trust system prevents exposure to unwanted content
- **Agency**: Control over personal story direction and participation

### For GMs
- **Powerful Tools**: Frontend and command tools for running engaging stories
- **Recognition**: XP and trust building for good GM performance
- **Support**: System helps track consequences and narrative connections
- **Flexibility**: Can adjust stories based on player actions and preferences

### For Story Owners
- **Control**: Ability to manage story direction and participant selection
- **Collaboration**: Tools for working with GMs and players
- **Quality Assurance**: Trust system ensures appropriate participants
- **Narrative Tracking**: Built-in tools for tracking story progression and consequences

## Future Considerations

### Planned Features
- **Story Templates**: Reusable story frameworks for common narrative structures
- **Automated Trust Calculation**: Algorithm for calculating trust scores from feedback
- **Story Analytics**: Tracking story engagement and completion rates
- **Cross-Story Consequences**: System for tracking how stories affect each other
- **Mentorship Programs**: Structured programs for developing new GMs and players

### Integration Opportunities
- **Calendar System**: Schedule story sessions and track progression
- **Communication Tools**: In-game messaging for story coordination
- **Resource Management**: Track story-related items, locations, and NPCs
- **Achievement System**: Recognition for story milestones and excellent participation

## Development Guidelines

When working on the Stories system:

1. **Player Safety First**: All features must consider trust and safety implications
2. **Narrative Focus**: Prioritize tools that improve storytelling over mechanical complexity
3. **Scalability**: Design for both small personal stories and large group narratives  
4. **Integration**: Consider how new features affect roster, scenes, and other apps
5. **User Experience**: GMs and players should find the system intuitive and helpful
6. **Data Integrity**: Careful attention to consequence tracking and narrative continuity

The Stories system represents the heart of Arx II's gameplay philosophy: that meaningful,
player-driven narratives are the foundation of an engaging gaming experience. Every feature
and design decision should support this core goal.
