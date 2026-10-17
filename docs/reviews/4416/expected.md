# #4416 real-testing pass: expected outcomes (written before running anything)

Sources: issue #4333 walkthrough C, design 5, Ruling 5, owner rules in the slice-4 dispatch,
demo GM tab screens 1-3 and Admin 6. Not from the code's output.

Cast (throwaway DB rt_4416): staff_4416 (staff); gm_4416 (Senior GM, owns "The Whitlow table";
plays "Warden Ashe"); e2e_test_account plays Tobiah Fenwright, Hobb Pennock, Wren Ashby, Orla Cobbe
(all seated at the table) and Brother Caddoc (not seated). Being: Wisket, a staff-created spirit
with no codex entry, declarations or temple. A second being "Ombrin" has one public worship
declaration (a god sign). A "Junior table" belongs to a Junior GM.

E1 Admin, steward inline: Wisket's change form shows a "Steward" inline. Choosing Junior table
   and saving is refused with "The table's GM is Junior GM; a steward's GM must be Senior GM."
   and nothing is saved. Choosing The Whitlow table saves; reloaded, the line beside it reads
   "GM level Senior GM. 4 active members. Stewards 0 other beings." and "Signs of a god: none".
E2 Admin, god sign: assigning The Whitlow table to Ombrin is refused, naming
   "1 character declares it as their public faith."
E3 Members only: Brother Caddoc (not seated) is refused pledging and praying to Wisket with
   "Wisket answers only to the members of one GM table." A seated member sacrifices an item to
   Wisket in a room with no shrine: accepted, room line "<name> sacrifices <item> to Wisket."
E4 Close goes to the steward: Tobiah closes his pledge (telnet `pledge/close`). His close line
   ends "Wisket's answer will come later." and no [VISION] arrives. The GM (telnet) is told
   "GM prompt [N] Being answer: Wisket answers Tobiah Fenwright (<tier>). gm prompt answer N |
   gm prompt dismiss N".
E5 Telnet answer: `gm prompts` lists it. `gm prompt answer N` lists only Wisket's answers at
   or below Tobiah's tier (never a higher tier), says whether text is allowed (only at Success or
   Critical Success) and names the catalogue clues. `gm prompt answer N answer=<id>` answers
   "Sent as a vision from Wisket." and Tobiah's session receives a [VISION] with that answer's
   delay text.
E6 Web free text: Hobb closes. On /tables/<id>?tab=beings the GM sees the pill "Being answer:
   Wisket answers Hobb Pennock (<tier>). Answer it?", opens the panel (pledge, tier, sacrificed
   item, prayer, the answers at the tier and below, Write free text, a clue picker, Send as
   Wisket, time left about 3 days). If Hobb's tier is Success or Critical Success: writing text,
   picking the mission clue and sending puts a vision on Hobb whose body is that text, naming
   Wisket, with "A mission came with it: Wisket mission clue." and Hobb holds the mission. If his
   tier is below Success, Write free text is disabled.
E7 Web dismiss: Wren closes. The GM clicks Dismiss on her pill: the pill goes, Wren gets a vision
   with one of Wisket's authored answers at or below her tier, and the prompt reads "Dismissed:
   an authored answer was drawn."
E8 Timeout: Orla closes. Her prompt is moved 3 days and a minute into the past (shell, the only
   stand-in for time passing); the tick `expire_steward_prompts()` returns 1; Orla gets an
   authored answer's vision; the prompt reads "No answer within 3 days: an authored answer was
   drawn."
E9 Below Success refuses free text on telnet: for a prompt below Success,
   `gm prompt answer N text=...` answers "Your own text can be sent on Success and Critical
   Success only." and nothing is sent.
E10 Table GM authoring: Edit Wisket on the table page; change the pledge favor target to 6 and
   save: the card then reads "favor target 6". Write a Critical Success answer: the coverage
   line for Critical Success turns from "not written" to "written", and the card's
   "N of 5 outcome tiers" count goes up by one.
E11 The scene GM queue (web) shows a being answer row with Open (link to the table's Beings tab)
   and Dismiss, when the GM views a scene they run.
