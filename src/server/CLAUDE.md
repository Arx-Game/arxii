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
- Runtime log files from Evennia server
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
