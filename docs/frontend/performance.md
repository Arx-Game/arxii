# Frontend Performance Strategy

This document outlines our approach to frontend performance optimization, focusing on bundle splitting and code organization.

## Current Architecture

Our Vite-based React frontend serves an Evennia-based MUD with these main feature areas:
- **Game Client**: Real-time gameplay interface with WebSocket communication
- **Character Management**: Roster, character sheets, and applications
- **Scenes**: Scene browsing and participation
- **Authentication & Profile**: Login, registration, user settings
- **Public Pages**: Homepage, news, statistics, lore

## Bundle Splitting Strategy

### Manual Chunking Approach

We use manual chunking to optimize caching and loading patterns:

```js
// vite.config.ts
manualChunks: {
  // Vendor libraries (rarely change, cache aggressively)
  'vendor-react': ['react', 'react-dom', 'react-router-dom'],
  'vendor-state': ['@reduxjs/toolkit', 'react-redux', '@tanstack/react-query'],
  'vendor-ui': ['@radix-ui/*', 'sonner', 'lucide-react'],

  // Feature chunks (load on-demand)
  'game-client': ['./src/game/*', './src/hooks/useGameSocket*'],
  'character-roster': ['./src/roster/*', './src/components/character/*'],
  'scenes': ['./src/scenes/*'],
  'auth-profile': ['./src/evennia_replacements/LoginPage*', './src/pages/ProfilePage*'],
  'home-public': ['./src/evennia_replacements/HomePage*']
}
```

### Chunking Rationale

**Vendor Chunks**: Separated by change frequency and usage patterns
- React core changes rarely, used everywhere
- UI libraries change occasionally, used heavily
- Utilities change rarely, used selectively

**Feature Chunks**: Aligned with user workflows
- Game client is heavy and only used by active players
- Character management is session-based usage
- Public pages are entry points with different performance needs

## Performance Benefits

### Caching Optimization
- **Vendor chunks**: Long-term caching (30+ days)
- **Feature chunks**: Medium-term caching (7-14 days)  
- **App shell**: Short-term caching (1-3 days)

### Loading Patterns
- **Critical path**: Home page loads only `vendor-react` + `home-public`
- **Progressive loading**: Game features load when accessed
- **Parallel loading**: Independent chunks load simultaneously

### Network Efficiency
- **Smaller initial bundles**: Faster Time to Interactive (TTI)
- **Targeted updates**: Feature changes don't invalidate vendor cache
- **HTTP/2 multiplexing**: Multiple small chunks vs one large bundle

## Tradeoffs and Monitoring

### Potential Issues to Watch

**1. Over-Chunking**
- **Symptom**: Too many HTTP requests, slower loading despite smaller files
- **Threshold**: >10 chunks for initial page load
- **Solution**: Consolidate related features or small chunks

**2. Chunk Size Imbalance**
- **Symptom**: One chunk much larger than others (>300kB after gzip)
- **Cause**: Feature grew beyond original scope
- **Solution**: Further split large features or move heavy deps to separate chunk

**3. Circular Dependencies**
- **Symptom**: Build warnings about chunk dependencies
- **Cause**: Cross-feature imports creating unexpected bundling
- **Solution**: Refactor shared code into explicit shared chunk

**4. Cache Invalidation Issues**
- **Symptom**: Users getting old versions after deployments
- **Cause**: Chunk boundaries changed, affecting content hashes
- **Solution**: Maintain stable chunk boundaries during refactoring

### Monitoring Metrics

**Bundle Analysis** (Monthly)
```bash
# Generate bundle visualization
pnpm build
npx rollup-plugin-visualizer dist/stats.html --open
```

**Key Metrics to Track**:
- Initial bundle size (target: <200kB gzipped)
- Largest chunk size (target: <500kB uncompressed)
- Number of chunks loaded on homepage (target: <5)
- Cache hit rate for vendor chunks (target: >90%)

**Performance Budget**
- **Homepage TTI**: <3s on 3G
- **Game client initial load**: <5s on 3G
- **Feature chunk load time**: <2s on 3G

### When to Re-evaluate

**Quarterly Reviews** - Check if:
- New major features require chunk restructuring
- Bundle sizes exceed performance budget
- User behavior patterns changed (analytics)
- New libraries significantly impact vendor chunks

**Immediate Re-evaluation Triggers**:
- Vite build warnings about chunk sizes >500kB
- Lighthouse performance scores drop >10 points
- User reports of slow loading (>5s to interactive)
- CDN costs increase significantly due to poor cache hit rates

## Implementation Notes

### Dynamic Imports for Route-Level Splitting
Consider upgrading to route-level splitting if manual chunks become insufficient:

```js
// App.tsx - if needed later
const GamePage = lazy(() => import('./game/GamePage'));
const CharacterSheetPage = lazy(() => import('./roster/pages/CharacterSheetPage'));
```

### Shared Code Strategy
- **Common components**: Keep in main bundle (used everywhere)
- **Feature utilities**: Keep within feature chunks
- **Heavy libraries**: Extract to dedicated vendor chunks if >100kB

### Testing Impact
- Test bundle sizes in CI/CD pipeline
- Monitor real user metrics (RUM) for loading performance
- A/B test chunk strategies if performance is critical

## Future Considerations

As the MUD grows, consider:
- **Service Worker caching** for offline-first game features
- **Module Federation** for plugin-based character sheet extensions
- **Edge-side includes** for personalized homepage content
- **Preloading strategies** for predictable user flows (game → character sheet)
