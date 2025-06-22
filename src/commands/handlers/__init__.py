"""
Handlers are the thin, reusable bridge between a DispatcherResult and FlowExecution
================================================================================

A **Handler** coordinates three jobs *only*:

1.  **Context & Stack Setup**
    • Create a fresh :class:`ContextData`.
    • Populate it with objects/values supplied by the *dispatcher* (caller, targets,
      parsed arguments, etc.).
    • Create—or receive—an :class:`EventStack` so every flow shares recursion
      protection and debugging information.

2.  **Run Prerequisite Events (optional)**
    • Iterate through ``prerequisite_events`` (a *list* passed in at call-time).
    • For each name, spin up a one-step mini-flow that *emits* the event,
      letting triggers veto or mutate context.
    • If **any** prerequisite flow ends with ``FlowState.STOP`` ⇒ raise
      :class:`CommandError` immediately.

3.  **Launch the Main FlowExecution**
    • Receive ``flow_name`` (or a ready ``FlowDefinition``) from the caller.
    • Build a :class:`FlowExecution`` with the shared context & stack and
      ``run()`` it.

Why so generic?
---------------
* A *single* concrete ``BaseHandler`` can service dozens of commands by
  accepting **runtime parameters** instead of hard-coding a flow.
* Sub-class only when a command needs an extra finishing step or exotic context
  priming; otherwise use ``BaseHandler`` as-is.

Typical Usage
-------------
```python
# inside a Command or Dispatcher
handler = BaseHandler()
handler.run(
    dr,                                # DispatcherResult
    flow_name="purchase_flow",         # main flow to execute
    prerequisite_events=(
        "prereq.volition",
        "prereq.has_money",
    ),
)
```
"""
