# Handlers – Developer Context

This file explains *why* the generic `BaseHandler` exists and *how* it is
meant to be wired up by commands / dispatchers.
Keep the text in simple ASCII; no reST markup, smart‑quotes, or emoji.

---

1. Purpose

---

A handler is the thin layer that turns the objects a dispatcher has
resolved into a running FlowExecution.  It is intentionally dumb:

* No parsing or object searches – the dispatcher already did that.
* No game rules – the flow, triggers, and service functions handle them.
* No knowledge of how output is shown – the flow produces its own effects.

2. Instantiation

---

```
handler = BaseHandler(
    flow_name="start_flight_flow",
    prerequisite_events=(
        "prereq.volition",
        "prereq.has_wings",
    ),
)
```

* `flow_name` is a string key for `FlowDefinition` objects.
* `prerequisite_events` is an iterable of event names to emit before the
  main flow runs.  Each event is emitted in a mini‑flow so triggers can
  veto or mutate the shared ContextData.

3. Public API

---

```
handler.run(caller=evennia_obj, **flow_vars)
```

* `caller`          – the Evennia object initiating the command.
* `**flow_vars`     – keyword args the dispatcher resolved (targets,
  amounts, directions, etc.).  Object values stay as
  *instances*; scalar values pass through unchanged.

4. Internal Workflow

---

1. The constructor makes an empty `ContextData` and `FlowStack`.

2. `run` caches an `ObjectState` for the caller and every object in
   `flow_vars` using `context.initialize_state_for_object`.

3. For each prerequisite event name:

   * Build a one‑step flow definition that emits the event.
   * Call `flow_stack.create_and_execute_flow`.
   * If the mini‑flow stops, raise `CommandError` immediately.

4. Lookup the requested `FlowDefinition`, build a `FlowExecution`, seed
   it with `flow_vars`, and run it via the flow stack.

5. Coding Guidelines

---

* Keep variable names descriptive; avoid one‑letter identifiers.
* Docstrings must be plain ASCII with no smart quotes.
* Never inspect or modify Evennia objects directly inside handlers.
* Never raise anything except `CommandError` for user‑facing failures.

6. Typical Pattern in a Command Class

---

```
class CmdFly(BaseCommand):
    def parse(self):
        # Dispatcher finds caller.location.obj_to_fly
        flow_vars = {
            "target": target_obj,
            "speed": desired_speed,
        }
        handler = BaseHandler(
            flow_name="start_flight_flow",
            prerequisite_events=("prereq.volition",),
        )
        handler.run(caller=self.caller, **flow_vars)
```

7. When to Subclass

---

Only subclass `BaseHandler` if you need to:

* Add extra context priming that cannot be expressed in flows.
* Post‑process the ContextData after the main flow runs.
* Wrap the whole execution in custom logging or metrics.

In all other cases, parameterise the base class and reuse it.

---

Keep this document in sync when the handler API changes.
