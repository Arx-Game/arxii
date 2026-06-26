# Custom action resolvers for non-template consent actions

Player-driven treatment of another PC's condition/alteration carries its own check/cost/reduction/backlash logic, so we registered a custom resolver in `world.scenes.action_services` for the `"treat_condition"` action key and routed it through `respond_to_action_request` before the standard `ActionTemplate`/`_resolve_standard_action` path; we rejected forcing treatment into the template machinery, which would have required special-casing or duplicating treatment logic inside a generic schema designed for action-template resolution. This gives non-template consent actions a single escape hatch while keeping most consent flows on the shared SCENE_ADAPTIVE pipeline.

> Status: accepted · Source: #1486, src/world/scenes/action_services.py
