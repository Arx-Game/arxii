# Goals glossary

**Goal**:
One thing a character is after, in the player's words, placed in a goal domain with points on it (and a status), where the invested points add as a situational bonus on checks that align with the goal. Characters distribute a fixed pool (30 points) across any number of goals in any domains; the domain bonus sums across goals sharing it (#3621).
_Avoid_: objective, ambition, aspiration

**Goal Horizon**:
Short term or long term (`GoalHorizon`). Goals are numbered within their horizon in the order added (`CharacterGoal.ordinal`), so play can name "my third short term goal" or "goal 1 under long term" (#3621).
_Avoid_: goal tier, goal length

**Goal Domain**:
A broad category of pursuit into which a character invests goal points, stored as a `ModifierTarget` row with `category='goal'` rather than as a hardcoded enum. The design set is Standing, Wealth, Knowledge, Mastery, Bonds, and Needs; some domains (e.g. Drives) are optional and require no point allocation.
_Avoid_: goal category, goal type
