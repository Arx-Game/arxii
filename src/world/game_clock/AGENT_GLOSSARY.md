# Game clock glossary

Domain-local vocabulary for `world/game_clock`. Root terms live in
[`AGENT_GLOSSARY_MAP.md`](../../../AGENT_GLOSSARY_MAP.md).

**Clock jump** (#5248, ADR-5248): a change of the game clock's date made by staff through
`set_clock`, measured from the in-game time the clock showed to the time it is set to.
A jump is forward or back and may be a minute or a century long. Pausing, resuming and
changing the speed are not jumps: they leave the date where it is.
_Avoid_: time skip (a forward jump made for a story reason; one use of a jump, not the
term), adjustment (the old name of the endpoint), rewind.

**Age handling** (`AgeHandling`, #5248): what a clock jump does to characters. **Aged**:
birth years stay and ages move with the calendar. **Kept**: birth years move with the
calendar and ages stay. A jump back is always Kept. On the staff page the two read
"Characters age" and "Characters keep their ages".
_Avoid_: jump mode, aging mode.

**Birth-year shift** (`GameClockHistory.birth_year_shift`): the number of calendar years a
Kept jump added to every character's birth year. Zero on every other change.
