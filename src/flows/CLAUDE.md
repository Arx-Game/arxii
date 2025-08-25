# Flows System - Game Logic Engine

Database-driven workflow engine that replaces hardcoded command logic. All game state changes flow through this system.

## Key Files

### `models/`
- **`flows.py`**: `FlowDefinition`, `FlowStepDefinition`, `FlowStack` - database-defined workflows
- **`triggers.py`**: `TriggerDefinition`, `Trigger` - event handlers that modify flows  
- **`events.py`**: `Event`, `EventTrigger` - runtime events for flow modification

### `object_states/`
- **`base_state.py`**: `BaseState` - mutable wrapper for Evennia objects during flows
- **`character_state.py`**: `CharacterState` - character permissions and state (`can_move`, `can_see`)
- **`room_state.py`**: `RoomState` - room scene and trigger management
- **`exit_state.py`**: `ExitState` - exit lock/unlock mechanics

### `service_functions/`
- **`communication.py`**: message sending, pose formatting, channels
- **`movement.py`**: room traversal, following, arrival/departure messages
- **`perception.py`**: looking, searching, inventory, object examination
- **`packages.py`**: package imports and behavior attachment

### `service_functions/serializers/`
- **`commands.py`**: command metadata for frontend
- **`communication.py`**: message formatting and character data
- **`room_state.py`**: room state for web client

### Core Engine
- **`flow_execution.py`**: `FlowExecution` - orchestrates flow step execution
- **`scene_data_manager.py`**: `SceneDataManager` - manages temporary scene state
- **`flow_stack.py`**: manages nested flow execution with cleanup

### Helpers (`helpers/`)
- **`hooks.py`**: Evennia integration points
- **`logic.py`**: flow logic utilities and condition evaluation
- **`parsing.py`**: text parsing and command arguments
- **`payloads.py`**: data structure management for flow variables

## Key Classes

- **`FlowExecution`**: Executes flow steps (conditionals, service calls, events)
- **`SceneDataManager`**: Creates and manages object states during execution
- **`BaseState`**: Temporary object wrapper with dynamic permissions
- **`FlowDefinition`**: Database model defining workflow steps
