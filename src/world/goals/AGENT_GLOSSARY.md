# Goals glossary

**Goal**:
A character's declared point allocation in a goal domain (with optional notes and a status), where the invested points add as a situational bonus on checks that align with the goal. Characters distribute a fixed pool (30 points) across their goals.
_Avoid_: objective, ambition, aspiration

**Goal Domain**:
A broad category of pursuit into which a character invests goal points, stored as a `ModifierTarget` row with `category='goal'` rather than as a hardcoded enum. The design set is Standing, Wealth, Knowledge, Mastery, Bonds, and Needs; some domains (e.g. Drives) are optional and require no point allocation.
_Avoid_: goal category, goal type
