# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git Workflow

**IMPORTANT: Never work directly on main.** Always create a feature branch before making changes:

```bash
git checkout -b feature-name
```

This prevents confusion when PRs are squash-merged and keeps main clean. After a PR is merged, delete the local branch and pull main:

```bash
git checkout main && git pull && git branch -D feature-name
```

**No GitHub CLI:** Do not use `gh` commands or GitHub CLI MCP tools. PRs are created manually through the GitHub web interface.

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

### Server Management
- `arx start` - Start the Evennia server (PREFERRED for running the server)
- `arx stop` - Stop the Evennia server
- `arx stop --hard` - Force-kill all Evennia processes (use when server hangs)
- `arx reload` - Reload the Evennia server (picks up code changes)
- `arx ngrok` - Start ngrok tunnel and auto-update .env for manual testing
  - Automatically updates `src/.env` with `FRONTEND_URL` and `CSRF_TRUSTED_ORIGINS`
  - Automatically updates `frontend/.env` with `VITE_ALLOWED_HOSTS` (for Vite dev server)
  - `arx ngrok --status` - Check if ngrok is running and show current URL
  - `arx ngrok --force` - Kill existing ngrok and restart with new tunnel
  - **Note:** ngrok URLs are ephemeral and dev-only. `frontend/.env` is gitignored to prevent committing ngrok domains.

**IMPORTANT:** Always use `arx start` to run the server, NOT `arx manage runserver`. The `arx start` command properly starts the Evennia server with portal and server processes, while `runserver` is a Django-only command that doesn't fully initialize Evennia.

### Linting and Formatting
- `ruff check .` - Run Python linting (includes import sorting, flake8 rules, and more)
- `ruff check . --fix` - Auto-fix Python linting issues where possible
- `ruff format .` - Format Python code (replaces black/isort, configured for line length 88)
- `pre-commit run --all-files` - Run all pre-commit hooks (now uses ruff)

### Frontend Development (in frontend/ directory)
- `pnpm dev` - Start Vite development server with Django API proxy
- `pnpm build` - Build production assets to `src/web/static/dist/`
- `pnpm lint` - Run ESLint on TypeScript/React files
- `pnpm lint:fix` - Run ESLint with auto-fix
- `pnpm format` - Format code with Prettier
- `pnpm typecheck` - Run TypeScript type checking

### Integration Testing
- `arx integration-test` - Automated integration test environment (highly automated!)
  - Requires `ALLOW_INTEGRATION_TESTS=true` in `src/.env` (safety check)
  - See `src/integration_tests/QUICKSTART.md` for usage guide
  - Automatically: starts ngrok, Django, frontend, registers test account, fetches verification email
  - Human verification: click verification link, confirm UI, test login
  - Press Ctrl+C to cleanup and restore everything

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

## Systems Index - IMPORTANT

**Before implementing features that touch multiple systems, consult `docs/systems/INDEX.md`.**

The systems index provides:
- Quick reference of all existing systems, their models, and key functions
- Integration points showing how systems connect
- Common queries and code patterns to reuse

This prevents reinventing existing functionality. For example, before building something that needs character traits, magic, or progression - check the index to find existing models and helper functions.

Individual system docs (e.g., `docs/systems/magic.md`) contain:
- Complete model listings with field descriptions
- Copy-pasteable code examples for common operations
- API endpoint references
- Frontend integration details

## Critical Evennia Migration Quirks

### Evennia makemigrations Solution
**FIXED: Custom makemigrations command prevents phantom Evennia library migrations**

We have a custom `makemigrations` command that prevents Django from creating problematic migrations in Evennia's library when our models have ForeignKeys to Evennia models.

```bash
# SAFE - our custom command prevents phantom Evennia migrations
arx manage makemigrations

# Still works - specify specific apps when needed  
arx manage makemigrations traits
```

**Details**: See `core_management/CLAUDE.md` for full technical documentation of the solution.

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
- **MyPy Type Checking**: Follow strategic type checking guidelines in `docs/mypy-strategy.md`. Add complex business logic systems to mypy, skip Django CRUD boilerplate
- **No Relative Imports**: Always use absolute imports (e.g., `from world.roster.models import Roster` not `from .models import Roster`) - relative imports are a flake8 violation for this project
- **Environment Variables**: Use `.env` file for all configurable settings, provide sensible defaults in settings.py
- **No Django Signals**: Never use Django signals (post_save, pre_save, etc.) - they create difficult-to-trace bugs. Always use explicit service function calls that can be tested and debugged easily
- **Migrations**: When model changes require migrations, use `arx manage makemigrations <app>` to generate them. Always use the `arx manage` commands for migrations to ensure correct Django settings are loaded. After generating, apply with `arx manage migrate`
- **Line Length**: Respect 88-character line limit even with indentation - break long lines appropriately
- **Model Instance Preference**: Always work with model instances rather than dictionary representations. Only serialize models to dictionaries when absolutely necessary (API responses, Celery tasks, etc.) using Django REST Framework serializers. This preserves access to model methods, relationships, and SharedMemoryModel caching benefits
- **Avoid Dict Returns**: Never return untyped dictionaries from functions. Use dataclasses, named tuples, or proper model instances for structured data. Dictionaries should only be used for wire serialization or when truly dynamic key-value storage is needed. Always prefer explicit typing over generic Dict[str, Any]
- **Separate Types Files**: Place dataclasses, TypedDicts, and other type declarations in dedicated `types.py` files within each app/module. This prevents circular import issues when the types need to be referenced across multiple modules. Import types using `from app.types import TypeName`
- **Don't add ordering unless necessary**: Ordering is not free. We should add it in viewsets, only at model.Meta level for sequential data that requires manual ordering, like Chapters or Episodes.
- **Prefer Inheritance Over Protocols**: Use concrete base classes with abstract methods instead of Protocol classes for type safety. All objects in our codebase inherit from shared base classes (BaseState, BaseHandler, etc.). When mypy compliance requires type annotations, prefer adding abstract methods to base classes rather than creating Protocol classes. This maintains clear inheritance hierarchies and ensures methods are actually implemented. Use Protocol only for true duck typing scenarios with external libraries.
- **Service Functions Use Model Instances**: Service functions should never accept slug strings for lookups. Always pass model instances or primary keys. Slugs are only for user-facing search APIs where users search by text and receive objects with IDs for subsequent operations. This applies to all internal service layer code.
- **Avoid Denormalized Foreign Keys**: When a model has a FK to a parent and optionally a FK to a child of that parent (e.g., `condition` + `stage` where stage implies condition), either make one FK derivable from the other or add `clean()` validation to ensure consistency. Don't create situations where FKs can contradict each other. If the child FK is nullable (null = applies to all), keep the parent FK for direct queries but validate the relationship.
- **TextChoices in constants.py**: Place Django TextChoices/IntegerChoices in a separate `constants.py` file rather than as nested classes inside models. This avoids circular import issues when serializers or other modules need to reference the choices, and makes it clearer these are shared constants.
- **No Management Commands**: Do not create Django management commands unless explicitly requested. Use existing tools: fixtures for seed data, the Django admin for data management, service functions for business logic, and the `arx` CLI for development tasks.

### Django-Specific Guidelines
**For all Django development (models, views, APIs, tests), follow the guidelines in `django_notes.md`.**

Key Django requirements:
- Use Django TextChoices/IntegerChoices for model field choices
- All ViewSets must have filters, pagination, and permission classes
- Use FactoryBoy for all test data with `setUpTestData` for performance
- Focus tests on application logic, not Django built-in functionality

### Migration Management for New Apps
**IMPORTANT: When working on a new app, avoid multiple migrations during development**
django_notes.md gives a more in-depth explanation of this strategy.

### Fixtures - NOT in Version Control
**IMPORTANT: Fixture files (JSON seed data) must NOT be committed to version control.**

- Fixtures are gitignored via `**/fixtures/*.json`
- Seed data is managed separately from code (via admin, shared storage, or documentation)
- If you create fixture files for local testing, they stay local
- Never use `git add -f` to force-add fixture files
- Do NOT create management commands to seed data - use Django's fixture system instead

## SharedMemoryModel Usage
- **Prefer SharedMemoryModel**: Use SharedMemoryModel for frequently accessed lookup data (traits, configuration tables, etc.) for better performance
- **Correct Import Path**: Always import from `evennia.utils.idmapper.models.SharedMemoryModel`
- **NEVER** import from `evennia.utils.models` - this path contains utilities that trigger Django setup during import and will break the Django configuration with "settings are not configured" errors
- **Example**:
  ```python
  # CORRECT - this works
  from evennia.utils.idmapper.models import SharedMemoryModel

  # WRONG - this breaks Django setup
  from evennia.utils.models import SharedMemoryModel
  ```
- **When to Use**: SharedMemoryModel is ideal for:
  - Trait definitions and conversion tables
  - Configuration data that changes rarely
  - Lookup tables for game mechanics
  - Any model that's read frequently but modified infrequently
