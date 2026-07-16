/**
 * Centralized URL management for the application
 * All route paths and URL generation should go through this file
 */

// Base paths
export const ROUTES = {
  HOME: '/',
  CHARACTERS: '/characters',
  SCENES: '/scenes',
  EVENTS: '/events',
  ROSTER: '/roster', // The character-browse route (bare /characters is a 404)
} as const;

// URL generation functions
export const urls = {
  // Character URLs
  character: (id: number | string) => `${ROUTES.CHARACTERS}/${id}`,

  // Scene URLs
  scene: (id: number | string) => `${ROUTES.SCENES}/${id}`,

  // Event URLs
  event: (id: number | string) => `${ROUTES.EVENTS}/${id}`,
  eventCreate: () => `${ROUTES.EVENTS}/new`,
  eventEdit: (id: number | string) => `${ROUTES.EVENTS}/${id}/edit`,
  eventsList: () => ROUTES.EVENTS,

  // List views
  scenesList: () => ROUTES.SCENES,
} as const;
