# Goals glossary

**Goal**:
One thing a character is after, in the player's words, placed in a goal domain with points on it (and a status), where the invested points add as a situational bonus on checks that align with the goal. Characters distribute a fixed pool (30 points) across any number of goals in any domains; the domain bonus sums across goals sharing it (#3621).
_Avoid_: objective, ambition, aspiration

**Secret Goal** (`CharacterGoal.is_secret`, #4106):
A goal kept to the character: the sheet shows it to the owner and staff only, whatever the goals section's visibility tier says, because the mark is applied in the goal builder before the tier is consulted. It still costs points and takes an ordinal. Marked at Final Touches ("Keep to yourself") and editable after through the goals endpoint. A journal entry keeps its own `is_public`; the goal is not named by the entry.
_Avoid_: private goal (the section tier is "private"; this is per goal), hidden goal.

**Goal Horizon**:
Short term or long term (`GoalHorizon`). Goals are numbered within their horizon in the order added (`CharacterGoal.ordinal`), so play can name "my third short term goal" or "goal 1 under long term" (#3621).
_Avoid_: goal tier, goal length

**Goal Domain**:
A broad category of pursuit into which a character invests goal points, stored as a `ModifierTarget` row with `category='goal'` rather than as a hardcoded enum. The design set is Standing, Wealth, Knowledge, Mastery, Bonds, and Needs; some domains (e.g. Drives) are optional and require no point allocation.
_Avoid_: goal category, goal type
