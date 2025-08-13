/**
 * Centralized URL management for the application
 * All route paths and URL generation should go through this file
 */

// Base paths
export const ROUTES = {
  HOME: '/',
  CHARACTERS: '/characters',
  SCENES: '/scenes',
  ROSTER: '/roster', // Legacy - use CHARACTERS instead
} as const;

// URL generation functions
export const urls = {
  // Character URLs
  character: (id: number | string) => `${ROUTES.CHARACTERS}/${id}`,
  characterEdit: (id: number | string) => `${ROUTES.CHARACTERS}/${id}/edit`,

  // Scene URLs
  scene: (id: number | string) => `${ROUTES.SCENES}/${id}`,
  sceneEdit: (id: number | string) => `${ROUTES.SCENES}/${id}/edit`,

  // List views
  charactersList: () => ROUTES.CHARACTERS,
  scenesList: () => ROUTES.SCENES,
} as const;

// Type-safe route parameters
export type RouteParams = {
  characterId: string;
  sceneId: string;
};
