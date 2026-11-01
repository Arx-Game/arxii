# D expectations (written before running). HEAD 72e6fad960038bf03f8dcf1a66eef9292a5529c0

Request: GET /api/combat/<id>/ twice on the running server, as Tomas (not owner, not GM) and as Marn (staff).
Garrick is masked as "scarred sellsword" and has a clash contribution.

Tomas's response:
1. Garrick's participant row: character_name "scarred sellsword", character_sheet_id null, persona_id == the mask persona's id.
2. No value anywhere (character_sheet_id, character_id, any sheet-keyed field) equals Garrick's sheet id.
3. Tomas's own row carries Tomas's sheet id.
4. The clash contributor carries participant_id (Garrick's seat id) and the mask name.
Marn's (GM/staff) response:
5. Every participant row carries its sheet id (Mira, Tomas, Garrick).
