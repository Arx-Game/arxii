from typing import Any, Self

from evennia.objects.objects import DefaultObject

from flows import models
from flows.flow_event import FlowEvent
from flows.flow_execution import FlowExecution
from flows.flow_stack import FlowStack
from flows.scene_data_manager import SceneDataManager

class FlowDefinitionFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.FlowDefinition: ...

    class Meta:
        model: type[models.FlowDefinition]

    name: str
    description: str

class FlowDefinitionWithInitialStepFactory(FlowDefinitionFactory):
    def __new__(cls, *args: Any, **kwargs: Any) -> models.FlowDefinition: ...
    def post_hook(self, create: bool, extracted: Any, **kwargs: Any) -> None: ...

class FlowStepDefinitionFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.FlowStepDefinition: ...

    class Meta:
        model: type[models.FlowStepDefinition]

    flow: models.FlowDefinition
    action: str
    variable_name: str
    parameters: dict[str, Any]
    parent_id: int | None

class EventFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.Event: ...

    class Meta:
        model: type[models.Event]

    name: str
    label: str

class TriggerDefinitionFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.TriggerDefinition: ...

    class Meta:
        model: type[models.TriggerDefinition]

    name: str
    flow_definition: models.FlowDefinition
    event: models.Event

class TriggerFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.Trigger: ...

    class Meta:
        model: type[models.Trigger]

    trigger_definition: models.TriggerDefinition
    obj: DefaultObject
    additional_filter_condition: dict[str, Any]

class SceneDataManagerFactory:
    def __new__(cls, **kwargs: Any) -> Self: ...
    def __call__(self) -> SceneDataManager: ...

class FlowStackFactory:
    def __new__(cls, **kwargs: Any) -> Self: ...
    def __call__(self) -> FlowStack: ...

    class Meta:
        model: type[FlowStack]

    trigger_registry: Any

class FlowExecutionFactory:
    def __new__(cls, **kwargs: Any) -> Self: ...
    def __call__(
        self,
        flow_definition: models.FlowDefinition | None = None,
        context: SceneDataManager | None = None,
        flow_stack: FlowStack | None = None,
        origin: Any | None = None,
        variable_mapping: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> FlowExecution: ...

    class Meta:
        model: type[FlowExecution]

    flow_definition: models.FlowDefinition | None
    context: SceneDataManager | None
    flow_stack: FlowStack | None
    origin: Any
    variable_mapping: dict[str, Any]

class FlowEventFactory:
    def __new__(cls, **kwargs: Any) -> Self: ...
    def __call__(self, **kwargs: Any) -> FlowEvent: ...

    class Meta:
        model: type[FlowEvent]

    event_type: str
    source: FlowExecution
    data: dict[str, Any]

    class Params:
        context: Any  # factory.Trait
