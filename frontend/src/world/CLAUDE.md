# World - Game World Type Definitions

Game world type definitions that mirror backend Django model enums and choices.

## Key Directories

### `character_sheets/`

- **`types.ts`**: Character attribute enums (Gender, etc.) mirroring backend choices

## Purpose

Provides frontend TypeScript types that match backend Django model choices, ensuring type safety across the full stack.

## Features

- **Enum Mirroring**: Frontend enums match Django TextChoices/IntegerChoices
- **Type Safety**: Consistent types between frontend and backend
- **Validation**: Form validation using same constraints as backend

## Integration Points

- **Character Sheets**: Gender and characteristic type definitions
- **Form Validation**: Consistent validation rules with backend
- **API Integration**: Type-safe API communication
