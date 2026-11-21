# CommandDescriptor Format

> **Status (ADR-4034, #4034):** the web client does not read these descriptors. It renders no
> form, drawer, menu or prompt for a telnet command. A person types a command into the composer,
> acts on a person through the persona menu (ADR-4030), and acts in combat through the typed
> panels. The server still builds and sends the descriptors, and this page records their shape
> for whoever decides what to do with them.

`CommandDescriptor` objects describe a command that has a web form. The server builds one per
command (`ArxCommand.to_payload()`, or `FrontendMetadataMixin.to_payload()` for a command that
is not an action), `serialize_cmdset()` gathers them for a character and its account, and
`commands_frame()` sends them as the args of the `commands` frame. The frame's kwargs carry
`names`, every name the character can type a command by, which the composer does read
(`Session.commandNames`).

The fields the server sends include an `action` (the command verb), a `prompt` template naming
each argument, a `params_schema` describing those arguments, and an optional `icon`, `name`,
`category` and `help`. The dataclass in `src/commands/` is the source of truth for the shape.

## Why the client stopped using them

The descriptors began as a "Quick Actions" panel (PRs #153, #154, #158 and #159, August 2025): a
side drawer that built a form from `params_schema` and sent the filled-in command text back. The
three-column game layout (PR #285, February 2026) removed its last mount, and nothing replaced it
with a form-driven surface for telnet commands. #4034 removed the components and the stored
descriptors from the client.
