"""Core flow system package.

The flows package provides a data-driven automation system. Game logic
is defined in database flows and triggers rather than hardcoded in
Python.

Key pieces:
 - SceneDataManager stores object states and events for a scene.
 - BaseState wraps Evennia objects with temporary state.
 - FlowEvent represents in-memory events that triggers react to.
 - FlowExecution runs a FlowDefinition and resolves variables.
 - FlowStack tracks running flows and prevents recursion.

Using these pieces together allows designers to build complex behaviour
with only database entries and simple service functions.
"""
