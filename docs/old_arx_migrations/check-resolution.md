# Check Resolution System

## Overview: What Worked in Arx I

Arx I went through 4 iterations of check systems. The final version was sophisticated and successful:

1. **Trait Values → Points**: Configurable lookup tables convert trait values to weighted points
2. **Points → Ranks**: Point totals map to exponential rank thresholds  
3. **Rank Difference → Chart**: Comparison selects from 17 different result charts
4. **0-100 Roll**: Random roll on selected chart determines final outcome

This system solved the "single trait dominance" problem and provided meaningful differentiation between character builds.

## Arx II Core Mechanics *(Preserving What Worked)*

### Step 1: Trait Combination
- **Primary Trait**: Main trait for the check (e.g., Strength for lifting)
- **Secondary Trait**: Optional supporting trait (e.g., Athletics skill)  
- **Combination Rules**: Sum, highest, lowest, or custom formulas
- **Modifiers**: Situational bonuses/penalties applied to final total

### Step 2: Point Conversion *(Details TBD)*
```
Trait Values → Weighted Points via Lookup Tables
```
- **Configurable Curves**: Database-driven conversion tables
- **Flexible Scaling**: Easy to adjust point values without code changes
- **Multiple Scales**: Different point curves for different trait types

### Step 3: Rank Calculation
```  
Point Totals → CheckRank via Exponential Thresholds
```
- **Rank Examples**: Rank 0 (0-19 pts), Rank 3 (60-79 pts), Rank 6 (150-224 pts)
- **Probability Enhancement**: Chance to "punch up" to next rank based on proximity
- **Dynamic Scaling**: Rank thresholds configurable via database

### Step 4: Chart Selection
```
(Roller Rank - Target Rank) → Result Chart Selection
```
- **17 Different Charts**: From "Impossible" to "Guaranteed Success"
- **Example**: Equal ranks → "Challenging" chart, +3 rank difference → "Easy" chart
- **Outcome Ranges**: Each chart has different success/failure probability distributions

### Step 5: Outcome Resolution
```
Random 1-100 Roll on Selected Chart → Final Result
```
- **Outcome Examples**: Catastrophic Failure, Marginal Success, Spectacular Success
- **Point Values**: Each outcome has associated point value for degree of success/failure
- **Narrative Guidance**: Results provide framework for describing what happened

## Integration with Arx II Systems

### Flow System Integration *(Design Needed)*
```python
# Conceptual flow step integration
check_result = character_state.make_check(
    primary_trait="strength",
    secondary_trait="athletics",
    difficulty_rank=3,
    modifiers={"heavy_load": -10, "adrenaline": +5}
)

if check_result.success_level >= "Success":
    # Continue to success flow path
else:
    # Handle failure with appropriate consequences
```

### Specialization Bonuses *(Implementation Unclear)*
- **Conditional Application**: Specializations add points if conditions met
- **Filter System**: Check context against specialization requirements
- **Examples**: +15 to crafting checks at night, +10 to social checks with nobles

### Class and Level Bonuses *(Architecture Open)*
- **Class Synergies**: Some class combinations may provide check bonuses
- **Level Benefits**: Higher levels might grant bonus points or reroll opportunities
- **Tier Advantages**: Crossing thresholds could unlock new check mechanics

## What We're Building Now vs Later

### Immediate Implementation *(Core Foundation)*
1. **Abstract Point System**: Framework for trait → point conversion
2. **Configurable Charts**: Database-driven result chart system
3. **Basic Integration**: Simple interface for flows to make checks
4. **Modifier Support**: System for applying situational bonuses/penalties

### Design Decisions Needed
1. **Point Conversion Curves**: What lookup tables for trait values → points?
2. **Rank Thresholds**: How should point totals map to ranks?
3. **Chart Variety**: Do we need all 17 charts or can we simplify?
4. **Specialization Mechanics**: How do conditional bonuses actually work?

### Future Extensions
1. **Advanced Modifiers**: Complex bonus calculation systems
2. **Multi-Step Checks**: Extended contests and complex resolution
3. **Group Checks**: Team cooperation and coordination mechanics
4. **Automated Difficulty**: Dynamic target ranks based on context

## Key Advantages of This System

### Player Understanding
- **Predictable**: Players can calculate their approximate rank
- **Transparent**: Modifiers and bonuses are clearly visible
- **Meaningful**: Investment in traits provides tangible benefits

### GM Flexibility  
- **Configurable**: All charts and conversions in database, not code
- **Scalable**: System works from mundane tasks to epic challenges
- **Narrative**: Rich outcome ranges support storytelling

### Technical Benefits
- **Performance**: Simple lookups and calculations
- **Maintainable**: Changes don't require code modifications
- **Testable**: Clear inputs and outputs for validation

## Open Questions

1. **Randomness Level**: How much should random rolls matter vs trait investment?
2. **Difficulty Scaling**: How do we set appropriate target ranks for different challenges?
3. **Failure Consequences**: How should different failure types affect ongoing scenes?
4. **Group Dynamics**: How do multiple characters cooperate on single checks?
5. **GM Tools**: What interfaces do player GMs need for managing check difficulty?
