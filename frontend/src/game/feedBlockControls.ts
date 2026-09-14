import { createContext } from 'react';

/**
 * What a reader may do to one block of the feed on this viewer's behalf
 * (#3856): fold it to a one-line stub, open it again, or take it out of this
 * view. `GameWindow` provides it from the session's own lists; nothing here
 * touches the server or anyone else's feed. Kept apart from the component so
 * the component file exports only components (fast refresh).
 */
export interface FeedBlockControls {
  minimized: ReadonlySet<string>;
  minimize: (key: string) => void;
  restore: (key: string) => void;
  dismiss: (key: string) => void;
}

export const FeedBlockControlsContext = createContext<FeedBlockControls | null>(null);
