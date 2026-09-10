# ADR-0288: XP stays account-scoped, and every movement of it is attributed to a character

**Status:** Accepted (#3748, 2026-09-10). Extends ADR-0053 (XP buys unlocks that gate,
never grant) without changing it. Makes ADR-0131's death-kudos cap read a real number.
Related ADR-0010.

**Context.** XP is earned, held and spent by the account. That is deliberate and stays:
a player's alts draw on one balance, so switching characters costs nothing and nobody
farms a second sheet for a first one. But the reviewer asked a question the account
balance cannot answer (2026-09-09): *"we do care what XP someone earned on a specific
character... we care how much XP someone invests and spends on a character, as we might
have some reimbursement mechanics to ease the pain of character loss."*

The machinery for that answer already existed and nothing fed it. `CharacterXP` and
`CharacterXPTransaction` had shipped; `XPTransaction.character` existed and was stamped
by some purchases. But `award_xp` took no character at all, so no earn was ever
attributed, and the only writer of `CharacterXP` was CG point conversion. ADR-0131 sized
the death-kudos cap on "the character's lifetime XP spend" by summing
`CharacterXP.total_spent` — a column no real spend ever incremented. The cap was, in
practice, the character's leftover CG points: a character with a lifetime of purchases
behind them was honoured no better than one who had never spent a point.

Five separate call sites debited the pool by hand — class-level unlocks, skill
breakthroughs, gift unlocks, thread-weaving unlocks and distinction sheet changes — each
repeating fetch-tracker, check, spend, write-receipt, and three of them not stamping the
character even on `XPTransaction`. The issue's own verified ledger named one of the five.
That is why the gap was invisible: nobody could see all five at once.

**Decision.** The balance stays the account's; **attribution is added beside it, not
under it.**

1. `award_xp` takes the earning character. It is **keyword-only with no default**, so
   every call site decides rather than inherits: nominations, journal posts and
   responses, goal progress, random scenes, first impressions and kudos claims name
   theirs; a GM story reward passes `None`, because running the scene is the GM's own
   work and no character earned it.
2. `spend_xp_for_character` is the **one seam every XP purchase debits through**. It
   moves the account pool, stamps `XPTransaction.character`, and credits the character's
   lifetime spend, in one transaction. Callers keep their own refusal wording by catching
   a typed `InsufficientXPError` that carries `required`/`available`.
3. **The per-character ledger is attribution, not a second pool.** Nothing is drawn from
   it. `total_spent` may exceed `total_earned`, because XP earned on one character is
   routinely spent on another, so `CharacterXP.clean()`'s no-overdraft rule now applies
   only to the `transferable=False` row CG conversion writes — the one row anything
   actually spends from.
4. One selector, `character_xp_ledger`, answers both questions, and the death-kudos cap,
   the admin and the sheet's panel all read it rather than re-aggregating.

**Alternatives rejected.** *Give each character its own XP pool.* This is what
"attributed to a character" most obviously means, and it is the wrong game: it punishes
playing a second character and makes character loss cost the balance rather than the
character. Attribution answers the reviewer's question without any of that.

*Derive lifetime spend from `XPTransaction` on read instead of keeping counters.* The
audit trail could be aggregated per character with no denormalized row at all. Rejected
because `CharacterXP` already exists and is already read by the cap, so deriving would
mean either deleting a shipped model or running two answers in parallel — and the locked
CG pool has no `XPTransaction` behind it at all (it never entered the account balance),
so a transaction-only derivation would silently drop it.

*Backfill past awards.* Alpha play state is declared resettable (ADR-0237), and there is
no honest way to attribute an earn that never recorded which character it was for. The
ledger is true from here forward.
