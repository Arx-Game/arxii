# Character Advancement System

## Revolutionary Change: From Skill-Based to Class/Level/Tier

Arx I was entirely skill-based with XP costs for everything. Arx II introduces a complex multi-layered progression system:

- **Classes**: Define progression paths and core skill requirements
- **Levels**: Power within current tier (1-5, 6-10, 11-15, etc.)  
- **Tiers**: Major power breakpoints requiring "Crossing the Threshold"
- **Development Points**: Activity-based incremental advancement
- **XP**: Reserved for major thresholds and unlocks

## Class and Level System *(Architecture Partially Defined)*

### Classes
- **Core Skills**: 3-5 skills required for level advancement in that class
- **Multi-Classing**: Characters can learn additional classes  
- **Prestige Classes**: Hybrid classes unlocked by multi-classing + threshold crossing
- **Class Benefits**: Each level grants unique perks/abilities beyond stat increases

### Level Advancement Process
```
Level 1 → Level 2: All core skills at 20 (2.0 displayed) + XP cost
Level 5 → Level 6: All core skills at 50 (5.0 displayed) + Threshold Crossing + XP
```

### Tiers and "Crossing the Threshold"
- **Tier 1**: Levels 1-5 (skill cap 50/5.0)
- **Tier 2**: Levels 6-10 (skill cap 100/10.0)  
- **Tier 3**: Levels 11-15 (skill cap 150/15.0)
- **Threshold Crossing**: Epic advancement event with massive lore significance

## Trait Advancement Mechanics

### 1-100 Scale with Dual Advancement Paths
- **Internal Values**: 1-100 point scale
- **Display**: 1.0-10.0 for player viewing
- **XP Thresholds**: Major advances at every 10 points (10→1.0, 20→2.0, 30→3.0)
- **Development**: Incremental advances between thresholds (11→1.1, 15→1.5)

### Advancement Types by Trait Category

**Stats** *(Mostly Fixed)*:
- **Creation**: Primary allocation during character creation
- **Advancement**: Very rare, story-driven opportunities only
- **Range**: Typically 10-50 for mortals (1.0-5.0 displayed)

**Core Skills** *(Required for Levels)*:
- **XP Gates**: Must spend XP at major thresholds (10, 20, 30, etc.)
- **Development**: Activity generates development points for incremental gains
- **Level Requirements**: All core skills must reach specific thresholds to advance

**Other Skills** *(Flexible Learning)*:
- **Development-Focused**: Primarily advanced through development points
- **Multi-Class Support**: Needed for learning additional classes
- **Practice Decay**: Unused skills accumulate penalties over time

### Practice Decay System *(Mechanics Undefined)*
- **Degradation**: Skills not used regularly lose effectiveness
- **Out of Practice**: Penalties accumulate until development points restore proficiency
- **Maintenance**: Regular use prevents decay
- **Recovery**: Development points remove decay penalties

## Multi-Prerequisite Advancement *(Complex System)*

Beyond simple XP/development costs, advancement may require:

### Narrative Prerequisites
- **Story Completions**: GM-marked narrative events
- **Character Achievements**: Specific recorded accomplishments
- **Personal Quests**: Custom challenges based on character history

### Relationship Requirements  
- **Character Bonds**: Connections to other characters at specific strengths
- **Mentor Relationships**: Master-level teachers for threshold crossing
- **Trust Networks**: Access through faction/organization standing

### Magical/Mystical Prerequisites
- **Resonance Scores**: Accumulation of specific magical alignments
- **Ritual Participation**: Involvement in significant magical events
- **Artifact Connections**: Bonds with specific magical items or locations

### Threshold Crossing Requirements *(Epic Events)*
- **Class Trials**: Specialized tests for each archetype
- **Sacrifice/Cost**: Meaningful character changes or losses
- **World Impact**: Character actions that affect the game world state
- **Community Recognition**: Acknowledgment from other high-tier characters

## Development Point System *(Mechanics TBD)*

### Sources of Development *(Design Open)*
Possible development point generation:
- **Activity-Based**: Using skills in meaningful contexts
- **Training Sessions**: Structured learning with teachers/mentors
- **Story Participation**: Involvement in significant narrative events
- **Social Interaction**: Relationship building and roleplay
- **Challenge Completion**: Overcoming obstacles and achieving goals

### Development Types *(Categories Unclear)*
May have separate development pools for:
- **Physical Training**: Combat skills, athletic abilities
- **Mental Development**: Academic skills, magical studies  
- **Social Growth**: Relationship skills, political abilities
- **Crafting Experience**: Trade skills, artistic pursuits
- **Mystical Advancement**: Magical abilities, spiritual growth

### Spending Mechanics *(Implementation Unknown)*
- **Incremental Costs**: Higher trait values require more development
- **Time Gates**: Some advancement requires waiting periods
- **Resource Requirements**: May need materials, locations, or assistance
- **Story Integration**: Advancement tied to character narrative arc

## GM Empowerment Tools *(Mostly Undesigned)*

Player GMs need tools to:
- **Mark Narrative Completions**: Record story milestone achievements
- **Adjust Development Rates**: Modify advancement speed for story pacing
- **Create Custom Prerequisites**: Design unique advancement requirements
- **Track Threshold Progress**: Monitor characters approaching tier advancement
- **Validate Requirements**: Check complex prerequisite chains

## Implementation Strategy

### Phase 1: Basic Framework *(Build Now)*
1. **Trait Value Storage**: 1-100 scale with development point tracking
2. **Simple Advancement**: XP thresholds and development spending
3. **Class Definitions**: Basic class structure with core skill requirements
4. **Level Tracking**: Character level and tier management

### Phase 2: Complex Prerequisites *(Design First)*  
1. **Achievement System**: Record and validate story accomplishments
2. **Relationship Integration**: Connect advancement to character bonds
3. **Narrative Markers**: GM tools for marking story completions
4. **Threshold Events**: Epic tier advancement mechanics

### Phase 3: Advanced Systems *(Add Later)*
1. **Practice Decay**: Unused skill degradation mechanics
2. **Development Sources**: Activity-based point generation
3. **Prestige Classes**: Multi-class combination unlocks
4. **Advanced GM Tools**: Complex prerequisite management

## Major Open Questions

### System Design
1. **Development Rates**: How fast should incremental advancement feel?
2. **Practice Decay**: How quickly do unused skills degrade?
3. **Threshold Frequency**: How often should characters cross tiers?
4. **Multi-Class Balance**: How do multiple classes interact?

### Prerequisites and Validation
5. **Automation vs Manual**: Which requirements can be automatically tracked?
6. **GM Authority**: How much can player GMs override prerequisites?
7. **Prerequisite Complexity**: How many requirements are too many?
8. **Failure Consequences**: What happens if threshold crossing fails?

### Integration
9. **Magic System**: How does magical advancement integrate?
10. **Connection Systems**: How do relationships affect advancement?
11. **Story Integration**: How tightly should advancement tie to narrative?
12. **Cross-Tier Balance**: How do we prevent higher tiers from trivializing content?

## Success Criteria

A successful advancement system should:
- **Reward Investment**: Time and effort spent should feel meaningful
- **Support Stories**: Advancement should enhance rather than interrupt narrative
- **Enable Choice**: Multiple viable paths to character development
- **Maintain Balance**: Power differences shouldn't break gameplay
- **Empower GMs**: Player GMs should have tools to support player growth
