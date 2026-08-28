/**
 * GatefoldPage — the public front page (#3305) for a VISITOR; the state-2
 * logged-in home for an authenticated account (#3412 slice 2).
 *
 * "Gatefold": a folio-styled cover + three chapters (Realms, Codex, Scenes)
 * + a closing "door" (registration/entry CTA). Forces the `arx` realm theme
 * for the duration of the page — Arx is the necropolis every visitor arrives
 * at first, regardless of which realm they eventually choose in character
 * creation. An authenticated account gets `<HallPage/>` INSTEAD of the
 * gatefold advertisement (ADR-0227: forced-arx is a visitor-advertisement
 * rule, not a logged-in rule) — the Hall renders in the viewer's own
 * realm/mode, so the forced-realm effect is skipped entirely while an
 * account is signed in.
 *
 * Visual source of truth: docs/superpowers/plans/gatefold-reference.html.
 */

import { useEffect } from 'react';
import { useRealmTheme } from '@/components/realm-theme-provider';
import { useAccount } from '@/store/hooks';
import { Cover } from './Cover';
import { RealmsChapter } from './RealmsChapter';
import { CodexChapter } from './CodexChapter';
import { ScenesChapter } from './ScenesChapter';
import { Door } from './Door';
import { HallPage } from './HallPage';
import './home.css';

export function GatefoldPage() {
  const { setForcedRealm } = useRealmTheme();
  const account = useAccount();

  useEffect(() => {
    if (account) return; // the Hall uses the viewer's own realm — never forced arx
    setForcedRealm('arx');
    return () => setForcedRealm(undefined);
  }, [setForcedRealm, account]);

  if (account) {
    return <HallPage />;
  }

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
