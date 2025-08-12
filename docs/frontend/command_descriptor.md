# CommandDescriptor Format

`CommandDescriptor` objects describe actions the webclient can present to the player. They appear in command payloads from the server and drive UI elements such as context menus, toolbar icons, and prompts. The format matches the dataclass defined on the backend and includes the following fields:

| field  | type | purpose |
|--------|------|---------|
| `label` | string | Human readable label shown to the player |
| `action` | string | Command verb sent back to the server |
| `params` | object | Additional parameters for the action |
| `params_schema` | object \| null | Description of arguments the client must collect |
| `icon` | string \| null | Optional icon identifier used by the UI |

## Examples

### Context menu

A list of descriptors can populate a right‑click menu for an object:

```json
[
  {
    "label": "Examine",
    "action": "look",
    "params": { "target": 42 },
    "icon": "search"
  },
  {
    "label": "Get",
    "action": "get",
    "params": { "target": 42 },
    "icon": "hand"
  }
]
```

### Icon action

Icons hint at the intent of quick‑access commands, such as toolbar buttons:

```json
{
  "label": "Inventory",
  "action": "open_panel",
  "params": { "target": "inventory" },
  "icon": "briefcase"
}
```

### Prompt

Descriptors can trigger a client‑side prompt before sending a command back to the server:

```json
{
  "label": "Rename",
  "action": "prompt",
  "params": {
    "command": "rename",
    "prompt": "Enter a new name"
  },
  "icon": "edit"
}
```

### Collecting parameters

Descriptors with a `params_schema` tell the client which inputs to gather before dispatching the command. If the schema defines one or two simple text fields, the webclient opens a modal dialog. More complex schemas open a side drawer with a form. The collected values merge into `params` when the `action` is sent back to the server.

When `icon` is omitted, the frontend should supply a generic placeholder.

The webclient consumes these descriptors to build interactive elements, as outlined in the [Webclient Game Plan](./game_client_plan.md). Each descriptor supplied in a command payload maps directly to a UI component that collects any needed parameters and dispatches the chosen `action` back to the server.
