import { useCallback, useState } from 'react';

/** Tracks action chips detached from the next prose submission. */
export function useDetachedActionIds() {
  const [detachedActionIds, setDetachedActionIds] = useState<number[]>([]);
  const handleDetach = useCallback((actionId: number) => {
    setDetachedActionIds((previous) =>
      previous.includes(actionId) ? previous : [...previous, actionId]
    );
  }, []);
  const handleUndoDetach = useCallback((actionId: number) => {
    setDetachedActionIds((previous) => previous.filter((id) => id !== actionId));
  }, []);
  const handlePoseSubmitted = useCallback(() => {
    setDetachedActionIds([]);
  }, []);
  return { detachedActionIds, handleDetach, handleUndoDetach, handlePoseSubmitted };
}
