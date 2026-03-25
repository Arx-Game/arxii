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
  const threading = useThreading(allInteractions, roomName);
  const [filterThreadKey, setFilterThreadKey] = useState<string | null>(null);

  const handleSelectThread = useCallback(
    (key: string) => {
      threading.setActiveThread(key);
      if (onComposerModeChange) {
        const thread = threading.threads.find((t) => t.key === key);
        if (thread) {
          onComposerModeChange(threadToComposerMode(thread, roomName));
        }
      }
    },
    [threading, roomName, onComposerModeChange]
  );

  const handleShowAll = useCallback(() => {
    threading.showAll();
    onComposerModeChange?.({
      command: 'pose',
      targets: [],
      label: `Pose \u2192 ${roomName}`,
    });
  }, [threading, roomName, onComposerModeChange]);

  const filterThread = filterThreadKey
    ? threading.threads.find((t) => t.key === filterThreadKey)
    : undefined;

  return (
    <div className="flex min-h-0 flex-1">
      {/* Thread Sidebar */}
      <ThreadSidebar
        threads={threading.threads}
        activeThreadKey={threading.activeThreadKey}
        visibleThreadKeys={threading.visibleThreadKeys}
        showingAll={threading.visibleThreadKeys.size === 0}
        onToggleThread={threading.toggleThreadVisibility}
        onSelectThread={handleSelectThread}
        onShowAll={handleShowAll}
        onOpenFilter={setFilterThreadKey}
      />

      {/* Scene Feed */}
      <div className="min-w-0 flex-1 overflow-y-auto">
        <SceneMessages
          sceneId={sceneId}
          filteredInteractions={threading.filteredInteractions}
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
          hiddenPersonaIds={threading.getHiddenPersonaIds(filterThreadKey)}
          onTogglePersona={(id) => threading.togglePersonaHidden(filterThreadKey, id)}
        />
      )}
    </div>
  );
}
