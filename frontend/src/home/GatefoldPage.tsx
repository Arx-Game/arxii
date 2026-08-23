/**
 * GatefoldPage — the public front page (#3305).
 *
 * "Gatefold": a folio-styled cover + three chapters (Realms, Codex, Scenes)
 * + a closing "door" (registration/entry CTA). Forces the `arx` realm theme
 * for the duration of the page — Arx is the necropolis every visitor arrives
 * at first, regardless of which realm they eventually choose in character
 * creation.
 *
 * Visual source of truth: docs/superpowers/plans/gatefold-reference.html.
 */

import { useEffect } from 'react';
import { useRealmTheme } from '@/components/realm-theme-provider';
import { Cover } from './Cover';
import { RealmsChapter } from './RealmsChapter';
import { CodexChapter } from './CodexChapter';
import { ScenesChapter } from './ScenesChapter';
import { Door } from './Door';
import './home.css';

export function GatefoldPage() {
  const { setForcedRealm } = useRealmTheme();

  useEffect(() => {
    setForcedRealm('arx');
    return () => setForcedRealm(undefined);
  }, [setForcedRealm]);

  return (
    <div className="gatefold">
      <Cover />
      <RealmsChapter />
      <CodexChapter />
      <ScenesChapter />
      <Door />
    </div>
  );
}
