# Tooling

**Status:** in-progress
**Depends on:** Areas, Items, Combat, Stories (for GM tools)

## Overview
Tools for players, GMs, and staff to interact with and manage the game world. Player tools focus on building and customizing spaces. GM tools are granular and level-gated — GMs can only do what their trust level allows. Staff tools are unrestricted for the one staffer coordinating the entire game.

## Key Design Points
- **Player building tools:** Room creation, decoration, furnishing. Economic cost of construction (buying and building rooms IC). Decorations give room statistics and bonuses. Everything from a cozy apartment to a massive fortress with research labs
- **GM tools (level-gated):** NPC creation within limits, combat management for encounters they run, reward distribution within a scaled range based on GM level. Newbie GMs get basic tools; veteran GMs get powerful world-shaping abilities
- **Staff tools:** Unrestricted "do anything" capability. The general-purpose commands that only the coordinating staffer needs. Creating areas, setting world state, managing GM promotions, overriding any system
- **Room building:** Both the mechanical creation of rooms (exits, descriptions, properties) and the player-facing economic version (purchasing land, commissioning construction, decorating)
- **NPC management:** GMs creating, placing, and controlling NPCs for their stories and adventures
- **Reward tools:** GMs granting XP, items, codex entries, legend — all within their level-appropriate caps
- **World state tools:** Staff-level tools for managing the living grid, triggering world events, updating canon time

## What Exists
- **Commands:** Room building commands (door creation, exit commands, room descriptors), movement commands, perception commands, character switching/sheet commands
- **Staff frontend:** Staff application detail page, extensive Django admin configuration
- **Areas system:** Room creation infrastructure exists through the areas app
- **No GM-specific tooling** — no level-gated commands or GM dashboard

## What's Needed for MVP
- GM command framework — level-gated command permissions scaling with GM trust
- GM NPC tools — creating, placing, customizing, and controlling NPCs within level limits
- GM combat tools — initiating encounters, managing combat flow, controlling enemy actions
- GM reward tools — granting XP, items, codex, legend within scaled caps
- Player room purchase flow — economic room acquisition with IC construction
- Decoration system — furnishing rooms with items that provide stats and bonuses
- Room stat calculation — how decorations and upgrades translate to room properties
- Staff world management — tools for the coordinating staffer to manage world state
- GM dashboard UI — web interface for GMs to manage their tables, NPCs, and active sessions
- Player building UI — web interface for room customization and decoration
- Builder documentation — in-game help for room creation and management

## Testing Infrastructure

### What Exists
- **Backend unit tests** — Django TestCase + DRF APITestCase per app, run via `arx test`
- **Frontend unit tests** — Vitest with React Testing Library, run via `pnpm test`
- **Production build smoke tests** — Playwright e2e tests that verify the built frontend loads,
  key routes render, no JS exceptions, and all chunks load. Run via `pnpm test:e2e`
- **Manual integration tests** — `arx integration-test` scaffolding for email verification flow
  (starts servers, creates test accounts, but human does the clicking)
- **Pre-commit hooks** — ruff, prettier, typecheck, custom linters

### What's Needed
- **Automated integration tests** — Replace the manual `arx integration-test` flow with Playwright
  tests that run the full stack (Django + frontend), log in, and exercise key user flows:
  - Registration and email verification
  - Character creation
  - Scene participation and interaction
  - Event creation and lifecycle
  - Codex browsing
- **CI pipeline** — Run backend tests, frontend tests, and e2e smoke tests on every PR.
  Integration tests can run on a schedule (nightly) since they need the full stack

### Coverage by System
| System | Backend Tests | Frontend Tests | E2E Smoke | Integration |
|--------|:---:|:---:|:---:|:---:|
| Events | yes | - | yes (route renders) | no |
| Scenes | yes | - | - | no |
| Roster/Characters | yes | - | - | no |
| Auth/Registration | yes | - | yes (login renders) | manual |
| Codex | yes | - | - | no |
| Stories | yes | - | - | no |

## Notes
