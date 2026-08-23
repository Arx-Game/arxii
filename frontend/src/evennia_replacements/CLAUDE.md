# Evennia Replacements - Custom Web Interface

Replaces default Evennia web interface with custom React implementation while maintaining compatibility with Evennia's authentication system.

## Key Files

### Authentication Pages

- **`LoginPage.tsx`**: Custom login interface with validation
- **`RegisterPage.tsx`**: Account registration with social auth support

### Home Interface

The public landing page (`/`) moved to `src/home/` — see `GatefoldPage.tsx`, `Cover.tsx`,
`RealmsChapter.tsx`, `CodexChapter.tsx`, `ScenesChapter.tsx`, `Door.tsx` (#3305). This app now
holds only the auth pages below plus the shared account/CSRF API layer.

### API Integration

- **`api.ts`**: CSRF-protected fetch functions for backend communication
- **`queries.tsx`**: React Query hooks for server state management
- **`types.ts`**: TypeScript definitions for API responses

## Key Features

- **CSRF Protection**: Automatic CSRF token handling for security
- **Social Authentication**: Integration with django-allauth for OAuth
- **Responsive Design**: Mobile-friendly responsive layout

## Integration Points

- **Django Backend**: Direct API integration with `/api/` endpoints
- **Evennia Auth**: Compatible with Evennia's authentication system
- **React Query**: Server state management with caching
- **Error Handling**: Graceful error display and recovery
