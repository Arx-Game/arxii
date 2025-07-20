class FlowExecution:
    """
    Manages the execution of a single flow instance.
    Contains the flow definition, a reference to shared context, the flow stack,
    the origin that triggered the flow, and a mapping of flow variables.
    It preloads all steps from the flow definition and provides helper methods
    for retrieving and updating flow variables, as well as determining the next step.
    """

    def __init__(
        self, flow_definition, context, flow_stack, origin, variable_mapping=None
    ):
        self.flow_definition = flow_definition
        self.context = context
        self.flow_stack = flow_stack
        self.origin = origin
        self.variable_mapping = (
            variable_mapping or {}
        )  # Maps flow variable names to their values
        self.steps = list(flow_definition.steps.all())
        self.current_step = self._get_entry_step()

    def _get_entry_step(self):
        """Finds and returns the entry step (the step with no parent)."""
        for step in self.steps:
            if step.parent_id is None:
                return step
        raise RuntimeError(
            f"No entry step found for FlowDefinition '{self.flow_definition.name}'."
        )

    def execute_current_step(self):
        """
        Executes the current step using the flow execution as context,
        and updates the current step to the next one.
        """
        if not self.current_step:
            return  # Flow is complete
        next_step = self.current_step.execute(self)
        self.current_step = next_step

    def get_variable(self, var_name):
        """Retrieves the value of a flow variable from this execution's mapping."""
        return self.variable_mapping.get(var_name)

    def resolve_flow_reference(self, value):
        """
        Resolves a value that may reference a flow variable (with optional dot notation).

        If the value is a string starting with '$', resolves it as a flow variable name,
        supporting dot notation for attribute access (e.g., "$foo.bar.baz").
        Otherwise, returns the value as-is.

        Raises:
            RuntimeError: If the variable or any attribute in the path does not exist.
        """
        if isinstance(value, str) and value.startswith("$"):
            path = value[1:].split(".")
            base = self.get_variable(path[0])
            if base is None:
                raise RuntimeError(f"Flow variable '{path[0]}' is undefined.")
            current = base
            for attr in path[1:]:
                current = getattr(current, attr, None)
                if current is None:
                    raise RuntimeError(f"Attribute '{attr}' not found on {base}.")
            return current
        return value

    def set_variable(self, var_name, value):
        """Sets the value of a flow variable in this execution's mapping."""
        self.variable_mapping[var_name] = value

    def get_service_function(self, function_name):
        """
        Retrieves a service function from an explicit mapping defined in service_functions.py.
        """
        from flows import service_functions

        try:
            return service_functions.get_service_function(function_name)
        except ValueError as err:
            raise ValueError(f"Service function '{function_name}' not found.") from err

    def get_next_child(self, current_step):
        """
        Returns the first child step of the given step, or None if none exist.
        """
        for step in self.steps:
            if step.parent_id == current_step.id:
                return step
        return None

    def get_next_sibling(self, current_step):
        """
        Returns the next sibling of the given step, or None if none exist.
        """
        if not current_step.parent_id:
            return None
        siblings = [s for s in self.steps if s.parent_id == current_step.parent_id]
        idx = siblings.index(current_step)
        return siblings[idx + 1] if idx + 1 < len(siblings) else None

    def execution_key(self):
        """
        Returns a unique key for this flow execution based on the flow definition and
        the origin.
        """
        return f"{self.flow_definition.id}:{str(self.origin)}"

    def get_trigger_registry(self):
        """
        Returns the trigger registry for the current flow execution's context/location.
        # TODO: Implement lookup of the correct TriggerRegistry for the current room/location.
        """
        pass
