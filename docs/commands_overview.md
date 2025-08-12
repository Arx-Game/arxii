# Command System Overview

Arx II keeps command classes intentionally simple. A command only interprets player
input and hands control to the flow engine. Every command declares one or more
**dispatchers** that pair a regular expression with a handler instance. The dispatcher
parses the text, resolves any referenced objects and then calls its handler.

Handlers perform permission checks and kick off flows. They can emit prerequisite
events before the main flow runs. Game rules and messaging belong in flows,
triggers or service functions—not in commands or handlers.

Because commands only glue these pieces together we test dispatchers, handlers
and flows rather than individual command classes.

## Frontend descriptors

Dispatchers expose a ``frontend_descriptor()`` method so the client can build
UI prompts dynamically. The descriptor returns an action name, optional icon and
``params_schema`` describing any arguments. Parameter entries at minimum define
their ``type``. Some dispatchers provide extra hints. For example,
``TargetDispatcher`` includes ``{"target": {"type": "string", "match":
"searchable_object"}}`` where ``match`` tells the frontend that the target must
be a searchable object in the caller's current context. Custom dispatchers may
set other ``match`` values to narrow the search criteria.

## Permission Checks

Handlers delegate permission logic to the caller's current state. Each state
implements `can_<action>` methods such as `can_move` or `can_open`. These
methods return `True` or `False` and always emit an intent event like
`move_attempt` or `open_attempt`. Triggers can react to that event in several
ways:

1. Start a flow that updates scene data so `can_<action>` fails on retry.
2. Cancel the parent flow before it reaches the service step.
3. Set ephemeral variables that block only this attempt.

For example, a trigger listening for `open_attempt` might mark the door locked
in scene data and cancel the flow so the door never opens.
