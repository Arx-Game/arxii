import { useState, useCallback } from 'react';
import { useSceneInteractions } from '../hooks/useSceneInteractions';
import { useThreading } from '../hooks/useThreading';
import type { Thread } from '../hooks/useThreading';
import { ThreadSidebar } from './ThreadSidebar';
import { ThreadFilterModal } from './ThreadFilterModal';
import { SceneMessages } from './SceneMessages';
import type { ComposerMode } from '@/game/components/CommandInput';

interface SceneInteractionPanelProps {
  sceneId: string;
  roomName: string;
  onComposerModeChange?: (mode: ComposerMode) => void;
  onAddTarget?: (personaName: string) => void;
}

function threadToComposerMode(thread: Thread, roomName: string): ComposerMode {
  switch (thread.type) {
    case 'room':
      return { command: 'pose', targets: [], label: `Pose \u2192 ${roomName}` };
    case 'place':
      return { command: 'tt', targets: [], label: `TT \u2192 ${thread.label}` };
    case 'whisper':
      return {
        command: 'whisper',
        targets: thread.participantPersonas.map((p) => p.name),
        label: `Whisper \u2192 ${thread.label.replace('Whisper: ', '')}`,
      };
    case 'target':
      return {
        command: 'pose',
        targets: thread.participantPersonas.map((p) => p.name),
        label: `Pose \u2192 ${thread.label}`,
      };
  }
}

export function SceneInteractionPanel({
  sceneId,
  roomName,
  onComposerModeChange,
  onAddTarget,
}: SceneInteractionPanelProps) {
  const { allInteractions, hasNextPage, fetchNextPage } = useSceneInteractions(sceneId);
  const {
    threads,
    filteredInteractions,
    selectedThreadKey,
    enabledThreadKeys,
    toggleThreadVisibility,
    showAll,
    getHiddenPersonaIds,
    togglePersonaHidden,
  } = useThreading(allInteractions, roomName);
  const [filterThreadKey, setFilterThreadKey] = useState<string | null>(null);

  // Destructured callbacks from useThreading are already stable (useCallback internally),
  // so this useCallback has stable deps and won't re-create unnecessarily. (Fix #4)
  const handleThreadClick = useCallback(
    (key: string) => {
      toggleThreadVisibility(key);
      if (onComposerModeChange) {
        const thread = threads.find((t) => t.key === key);
        if (thread) {
          onComposerModeChange(threadToComposerMode(thread, roomName));
        }
      }
    },
    [toggleThreadVisibility, threads, roomName, onComposerModeChange]
  );

  const handleShowAll = useCallback(() => {
    showAll();
    onComposerModeChange?.({
      command: 'pose',
      targets: [],
      label: `Pose \u2192 ${roomName}`,
    });
  }, [showAll, roomName, onComposerModeChange]);

  const filterThread = filterThreadKey ? threads.find((t) => t.key === filterThreadKey) : undefined;

  return (
    <div className="flex min-h-0 flex-1">
      {/* Thread Sidebar */}
      <ThreadSidebar
        threads={threads}
        selectedThreadKey={selectedThreadKey}
        enabledThreadKeys={enabledThreadKeys}
        isUnfiltered={enabledThreadKeys.size === 0}
        onThreadClick={handleThreadClick}
        onShowAll={handleShowAll}
        onOpenFilter={setFilterThreadKey}
      />

      {/* Scene Feed */}
      <div className="min-w-0 flex-1 overflow-y-auto">
        <SceneMessages
          sceneId={sceneId}
          filteredInteractions={filteredInteractions}
          onAddTarget={onAddTarget}
        />
        {hasNextPage && (
          <button onClick={() => fetchNextPage()} className="mt-4 px-4">
            Load More
          </button>
        )}
      </div>

      {/* Filter Modal */}
      {filterThread && filterThreadKey && (
        <ThreadFilterModal
          open={!!filterThreadKey}
          onClose={() => setFilterThreadKey(null)}
          thread={filterThread}
          hiddenPersonaIds={getHiddenPersonaIds(filterThreadKey)}
          onTogglePersona={(id) => togglePersonaHidden(filterThreadKey, id)}
        />
      )}
    </div>
  );
}
