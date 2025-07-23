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
