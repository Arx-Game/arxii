# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Essential Commands

### Development Setup
- `uv sync` - Install Python dependencies
- `uv venv` - Create virtual environment
- `pre-commit install` - Install pre-commit hooks

### Common Development Commands
- `arx test` - Run Evennia tests (run `arx manage migrate` first if fresh environment)
- `arx test <args>` - Run specific tests with additional arguments
- `arx shell` - Start Evennia Django shell with correct settings
- `arx manage <command>` - Run arbitrary Django management commands
- `arx build` - Build docker images (runs `make build`)

### Linting and Formatting
- `black .` - Format Python code (configured for line length 88)
- `isort .` - Sort Python imports (black profile)
- `flake8` - Run Python linting
- `pre-commit run --all-files` - Run all pre-commit hooks

### Frontend Development (in frontend/ directory)
- `pnpm dev` - Start Vite development server with Django API proxy
- `pnpm build` - Build production assets to `src/web/static/dist/`
- `pnpm lint` - Run ESLint on TypeScript/React files
- `pnpm lint:fix` - Run ESLint with auto-fix
- `pnpm format` - Format code with Prettier
- `pnpm typecheck` - Run TypeScript type checking

## Architecture Overview

### Core Structure
Arx II is an Evennia-based MUD (Multi-User Dungeon) with a sophisticated flow-based command system:

1. **Commands** (`src/commands/`) - Simple command classes that only interpret input and delegate to dispatchers
2. **Dispatchers** - Parse text using regex and call handlers with resolved objects
3. **Handlers** (`src/commands/handlers/`) - Perform permission checks and trigger flows
4. **Flows** (`src/flows/`) - Core game logic engine that handles state changes and messaging
5. **Triggers** - React to events and can modify flow execution

### Key Components

#### Flow System (`src/flows/`)
- **Flow Engine** - Executes sequences of steps based on triggers and events
- **Object States** - Character, room, exit states that implement permission methods (`can_move`, `can_open`, etc.)
- **Service Functions** - Handle communication, movement, perception
- **Scene Data Manager** - Manages temporary scene state

#### Command Architecture
Commands follow the pattern: Input → Dispatcher → Handler → Flow → Service Function
- Commands are intentionally simple and only glue components together
- All game logic lives in flows, triggers, or service functions
- Permission checks delegate to object states which emit intent events

#### Evennia Integration
- Built on Evennia framework with Django backend
- Custom typeclasses in `src/typeclasses/`
- Server configuration in `src/server/conf/`
- Web interface components in `src/web/`

### Project Structure
- `src/cli/arx.py` - CLI entry point with typer-based commands
- `src/flows/` - Flow engine and game logic
- `src/commands/` - Command system with dispatchers and handlers
- `src/typeclasses/` - Evennia object definitions
- `src/server/` - Evennia server configuration
- `docs/` - Documentation including command system overview

### Development Environment
- Python 3.13+ managed by mise
- Node.js v20 for web assets
- uv for dependency management
- Environment file: `src/.env`
- Working directory should be `src/` for Django commands

## Critical Evennia Migration Quirks

### Evennia makemigrations Gotcha
**ALWAYS specify app name when running makemigrations with FKs to Evennia models**

```bash
# WRONG - will create migrations in Evennia library
arx manage makemigrations

# CORRECT - specify our app
arx manage makemigrations accounts
arx manage makemigrations evennia_extensions
arx manage makemigrations world
```

**Problem**: If any of our models have ForeignKeys to Evennia models (Account, ObjectDB, etc.), running `makemigrations` without specifying an app will create migrations in the Evennia library itself to add our typeclasses as proxy models. These migrations:
1. Should be ignored (never commit them)
2. Will not exist in the library for other installations  
3. Will break if our migrations depend on them

**Solution**: Always specify the app name when running makemigrations.

### Evennia Integration Strategy
- **Use Evennia Models**: Keep using Evennia's Account, ObjectDB, etc. - don't reinvent the wheel
- **Extend via evennia_extensions**: Use the evennia_extensions app pattern for data storage that extends Evennia models
- **No Attributes**: Replace all Evennia attribute usage with proper Django models through evennia_extensions
- **Item Data System**: Consider reusing ArxI's item_data descriptor system for routing data to different storage models

### Database Design Principles
- **No JSON Fields**: Avoid JSONField - each setting/configuration should be a proper column with validation and indexing
- **Proper Schema**: Use foreign keys, proper data types, and database constraints
- **Queryable Data**: All data should be easily queryable with standard Django ORM

### Code Quality Standards
- **No Relative Imports**: Always use absolute imports (e.g., `from world.roster.models import Roster` not `from .models import Roster`) - relative imports are a flake8 violation for this project
- **Environment Variables**: Use `.env` file for all configurable settings, provide sensible defaults in settings.py
- **No Django Signals**: Never use Django signals (post_save, pre_save, etc.) - they create difficult-to-trace bugs. Always use explicit service function calls that can be tested and debugged easily
- **Line Length**: Respect 88-character line limit even with indentation - break long lines appropriately
