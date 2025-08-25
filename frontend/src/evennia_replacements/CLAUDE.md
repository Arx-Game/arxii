# Evennia Replacements - Custom Web Interface

Replaces default Evennia web interface with custom React implementation while maintaining compatibility with Evennia's authentication system.

## Key Files

### Authentication Pages

- **`LoginPage.tsx`**: Custom login interface with validation
- **`RegisterPage.tsx`**: Account registration with social auth support

### Home Interface

- **`HomePage.tsx`**: Main landing page with game status
- **`NewPlayerSection.tsx`**: New player onboarding information
- **`NewsTeaser.tsx`**: Latest news and updates display
- **`StatusBlock.tsx`**: Server status information
- **`StatsCard.tsx`**: Game statistics display
- **`RecentConnected.tsx`**: Recently connected players

### Lore Interface

- **`LoreTabs.tsx`**: Game lore and documentation tabs

### API Integration

- **`api.ts`**: CSRF-protected fetch functions for backend communication
- **`queries.tsx`**: React Query hooks for server state management
- **`types.ts`**: TypeScript definitions for API responses

## Key Features

- **CSRF Protection**: Automatic CSRF token handling for security
- **Social Authentication**: Integration with django-allauth for OAuth
- **Real-time Status**: Live server and player statistics
- **Responsive Design**: Mobile-friendly responsive layout

## Integration Points

- **Django Backend**: Direct API integration with `/api/` endpoints
- **Evennia Auth**: Compatible with Evennia's authentication system
- **React Query**: Server state management with caching
- **Error Handling**: Graceful error display and recovery
