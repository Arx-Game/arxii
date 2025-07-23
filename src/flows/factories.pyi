from typing import Any, Dict, Optional, Type

from evennia.objects.objects import DefaultObject

from flows import models
from flows.flow_event import FlowEvent
from flows.flow_execution import FlowExecution
from flows.flow_stack import FlowStack
from flows.scene_data_manager import SceneDataManager

class FlowDefinitionFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.FlowDefinition: ...

    class Meta:
        model: Type[models.FlowDefinition]

    name: str
    description: str

class FlowDefinitionWithInitialStepFactory(FlowDefinitionFactory):
    def __new__(cls, *args: Any, **kwargs: Any) -> models.FlowDefinition: ...
    def post_hook(self, create: bool, extracted: Any, **kwargs: Any) -> None: ...

class FlowStepDefinitionFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.FlowStepDefinition: ...

    class Meta:
        model: Type[models.FlowStepDefinition]

    flow: models.FlowDefinition
    action: str
    variable_name: str
    parameters: Dict[str, Any]
    parent_id: Optional[int]

class EventFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.Event: ...

    class Meta:
        model: Type[models.Event]

    key: str
    label: str

class TriggerDefinitionFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.TriggerDefinition: ...

    class Meta:
        model: Type[models.TriggerDefinition]

    name: str
    flow_definition: models.FlowDefinition
    event: models.Event

class TriggerFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> models.Trigger: ...

    class Meta:
        model: Type[models.Trigger]

    trigger_definition: models.TriggerDefinition
    obj: DefaultObject
    additional_filter_condition: Dict[str, Any]

class SceneDataManagerFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> SceneDataManager: ...

class FlowStackFactory:
    def __new__(cls, **kwargs: Any) -> FlowStack: ...

    class Meta:
        model: Type[FlowStack]

class FlowExecutionFactory:
    def __new__(
        cls,
        flow_definition: Optional[models.FlowDefinition] = None,
        context: Optional[SceneDataManager] = None,
        flow_stack: Optional[FlowStack] = None,
        origin: Optional[Any] = None,
        variable_mapping: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> FlowExecution: ...

    class Meta:
        model: Type[FlowExecution]

    flow_definition: Optional[models.FlowDefinition]
    context: Optional[SceneDataManager]
    flow_stack: Optional[FlowStack]
    origin: Any
    variable_mapping: Dict[str, Any]

class FlowEventFactory:
    def __new__(cls, *args: Any, **kwargs: Any) -> FlowEvent: ...

    class Meta:
        model: Type[FlowEvent]

    event_type: str
    source: FlowExecution
    data: Dict[str, Any]

    class Params:
        context: Any  # factory.Trait
