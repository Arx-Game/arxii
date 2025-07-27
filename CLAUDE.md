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
