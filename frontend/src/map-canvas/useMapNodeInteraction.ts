/**
 * Shared click/keyboard-activation wiring for map canvas node components
 * (RoomNode, PlaceNode, and #2449's world-builder nodes) — treats a node's
 * wrapper `div` as a button: Enter/Space activates it the same as a click.
 * Visuals and badges stay component-specific; only the interaction plumbing
 * is shared.
 */

import type { KeyboardEvent } from 'react';

export interface MapNodeInteractionProps {
  role: 'button';
  tabIndex: 0;
  onClick: () => void;
  onKeyDown: (event: KeyboardEvent) => void;
}

export interface UseMapNodeInteractionArgs {
  onSelect: () => void;
}

export function useMapNodeInteraction({
  onSelect,
}: UseMapNodeInteractionArgs): MapNodeInteractionProps {
  return {
    role: 'button',
    tabIndex: 0,
    onClick: onSelect,
    onKeyDown: (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        onSelect();
      }
    },
  };
}
