---
name: outbound-frame-reviewer
description: Checks that a server-to-client websocket message a diff sends arrives as the one frame the web client dispatches on. Use when a diff adds or changes a `session.msg`, `obj.msg` or `account.msg` call that carries a structured payload (anything but plain `text`), adds a frame name to `web/webclient/message_types.py`, or adds a case to the message switch in `frontend/src/hooks/useGameSocket.ts`, and when reviewing one. Catches the reply the server sends and the page never hears, while every test that reads the mock's keywords stays green.
tools: Bash, Read, Grep, Glob
model: sonnet
---

Review a diff for an outbound websocket message whose shape on the wire is not the
shape the client dispatches on. #4774 is the worked example: `execute_action` replied
with `session.msg(type="action_result", kwargs={...})`. Evennia turns every keyword
given to `msg` into its own frame named after the keyword, so the browser received
`["type", ["action_result"], {}]` and `["kwargs", [], {...}]`. The client switches on the
frame name, handled neither, and for six months no web action's reply reached a
listener: say and whisper drafts were never acknowledged, steal never resolved, and
panels never refreshed after withdraw, equip or take a breath. Every test passed,
because the tests read `session.msg.call_args.kwargs` as one dict.

For each structured `msg` call in the diff:

1. Name the frame the client will receive. It is the keyword (`msg(action_result=((),
   payload))` is one frame named `action_result`), or each key of a `**{...}` splat.
   Two keywords are two frames; `options` is the only keyword that is not one.
2. Find the client's handler for that name in `useGameSocket.ts` (the
   `WS_MESSAGE_TYPE` switch) and confirm the payload sits where the handler reads it,
   usually `kwargs`, with `args` empty. A frame name no handler matches is dropped
   silently.
3. Read the test that covers the send. It must assert one keyword naming the frame
   and the `(args, kwargs)` value, not pick fields out of `call_args.kwargs`. A helper
   that flattens the call into one dict proves nothing about the wire
   (`src/web/tests/test_execute_action_inputfunc.py`'s `_result_payload` is the fixed
   shape).
4. For a new frame name, check `message_types.py`, the frontend constant and the
   handler were added together; a backend-only name reaches nothing.

The `msg-frame-keywords` hook (`tools/lint_msg_frame_keywords.py`) rejects the
`type=`/`kwargs=` spellings; it cannot see a wrong frame name or a payload in the
wrong slot. Where the diff's claim is that a page reacts to the reply, ask for a live
run that shows the frame arriving (Playwright `page.on('websocket')` logs it).

Report each finding with file and line, the frame the client actually receives, and
what the page does instead.
