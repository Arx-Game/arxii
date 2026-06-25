# New subsystems are submodules of existing apps

A new subsystem defaults to a submodule of an existing app (e.g. `areas/positioning/`) rather than a
new Django app; we rejected spinning up a fresh app per subsystem. Many small apps make a convoluted,
collision-prone migration graph, so we only create a new app when the boundary genuinely warrants it.

> Status: accepted · Source: memory
