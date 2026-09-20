# Server - Evennia Configuration

Evennia server configuration and customization. Contains settings and hooks for integrating Arx II systems with Evennia framework.

## Key Directories

### `conf/`
- **`settings.py`**: Main Django/Evennia configuration file
- **`at_initial_setup.py`**: Server initialization hooks
- **`at_server_startstop.py`**: Server startup/shutdown hooks
- **`cmdparser.py`**: Command parsing configuration
- **`connection_screens.py`**: Login/connection screen customization
- **`lockfuncs.py`**: Custom lock function definitions
- **`secret_settings.py`**: Environment-specific secret settings
- **`test_settings.py`**: Testing configuration overrides
- **`web_plugins.py`**: Web interface plugin configuration

### `logs/`
- Default runtime log location (`settings.LOG_DIR`, env-driven; production uses `/var/log/arxii`)
- Channel logs, HTTP request logs, server logs

## Key Files

### `conf/settings.py`
- Environment-based configuration using .env file
- Third-party integrations (Cloudinary, django-allauth)
- Database configuration
- App registration for all world/ and core systems
- Security settings and CORS configuration

### `conf/at_initial_setup.py`
- Database initialization on first server start
- Default data creation and system setup

### `conf/web_plugins.py`
- Custom web interface plugins
- Integration with React frontend
- API endpoint configuration

## Configuration Features

- **Environment Variables**: All secrets and configurable settings via .env
- **12-Factor App Principles**: Proper configuration management
- **Third-Party Integration**: Cloudinary, social auth, email services
- **Development/Production**: Different settings for different environments

## Integration Points

- **World Apps**: Registers all game-specific Django apps
- **Flow System**: Configures flow execution environment
- **Web Interface**: Bridges Evennia and React frontend
- **Security**: CORS, authentication, and permission configuration

## The `text_frame_options` seam (#3857, #3933)

`conf/serversession.py:ServerSession.data_out` (wired by `SERVER_SESSION_CLASS`) is the
one place a per-session tag reaches a `text` frame. While `session.ndb.text_frame_options`
holds a dict, every `text` frame leaving that session carries those options merged into
its own. `merge_text_options` coerces a bare string to Evennia's `(text, {options})`
tuple form, and **the frame's own keys win** over the session's, so an option a command
already set (#3856's `type`) survives the merge.

The slot has two writers, so both save the previous value and restore it in a `finally`,
and both merge rather than replace:

- `conf/inputfuncs.py:text` sets `{"console": True}` for a line the web composer's
  Commands mode sends (`console=True` on the inbound frame). The client routes tagged
  frames to its console sheet, never the column.
- `typeclasses/characters.py:Character.at_post_puppet` sets `{"on_entry": True}` around
  the joining session's own `look`. The web client drops that frame because the room
  panel already shows the room; telnet still prints the entry look. Merging is what
  keeps a console-mode `@ic` tagged `console` on that look as well.

Command execution is synchronous for the commands this exists for. Output a command
schedules for later is not tagged and lands where it always did. The option keys live in
`core/wire_options.py:TextFrameOption`, never as free strings (ADR-0306).
Tests: `web/tests/test_console_capture.py`.

## The `puppet` inputfunc (#3933)

`conf/inputfuncs.py:puppet` is the web client's puppet handshake. The client sends
`["puppet", [], {"character": <name>}]` on every socket open, in place of the `@ic <name>`
text line it used to send, and the inputfunc reaches the same idempotent
`Account.puppet_character_in_session`. It sends no text of its own:

- **Success** is the `puppet_changed` broadcast that puppeting already emits. The client
  treats a `puppet_changed` naming this socket's character as its confirmation.
- **Refusal** is `session.msg(command_error={"error": <reason>, "command": "puppet"})`,
  the existing `command_error` frame shape, which the client toasts. Three refusals
  reach it: no account on the session, a missing or blank `character`, and a name that is
  not exactly one of `account.get_available_characters()`.

`@ic` stays the telnet spelling and is unchanged.
