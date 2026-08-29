/**
 * GatefoldPage — the public front page (#3305) for a VISITOR; the state-2
 * logged-in home for an authenticated account (#3412 slice 2); and a
 * straight-through redirect to `/game` for an account with a LIVE in-world
 * connection (#3412 slice 4, state-3 mode coherence).
 *
 * "Gatefold": a folio-styled cover + three chapters (Realms, Codex, Scenes)
 * + a closing "door" (registration/entry CTA). Forces the `arx` realm theme
 * for the duration of the page — Arx is the necropolis every visitor arrives
 * at first, regardless of which realm they eventually choose in character
 * creation. An authenticated account gets `<HallPage/>` INSTEAD of the
 * gatefold advertisement (ADR-0227: forced-arx is a visitor-advertisement
 * rule, not a logged-in rule) — the Hall renders in the viewer's own
 * realm/mode, so the forced-realm effect is skipped entirely while an
 * account is signed in. An account whose active character is CONNECTED
 * (not merely selected) skips the Hall entirely and lands in `/game` —
 * the Hall is a menu for picking a character, not a waiting room for one
 * already in play.
 *
 * Visual source of truth: docs/superpowers/plans/gatefold-reference.html.
 */

import { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { useRealmTheme } from '@/components/realm-theme-provider';
import { useAuthStatus } from '@/evennia_replacements/queries';
import { useAppSelector } from '@/store/hooks';
import { Cover } from './Cover';
import { RealmsChapter } from './RealmsChapter';
import { CodexChapter } from './CodexChapter';
import { ScenesChapter } from './ScenesChapter';
import { Door } from './Door';
import { HallPage } from './HallPage';
import './home.css';

export function GatefoldPage() {
  const { setForcedRealm } = useRealmTheme();
  // Gate the visitor/Hall split on the resolved account query, not the Redux
  // mirror: Redux is null until /api/user/ answers, so gating on it painted
  // every logged-in player the full visitor Gatefold (and forced the arx
  // realm, 0.8s color churn included) for one roundtrip on each hard load of
  // `/`. Deliberate tradeoff: a visitor's very first paint is now a quiet
  // blank beat instead of the instant advertisement — players load `/` many
  // times a day, visitors see it once, so the flash lands on the rarer
  // audience. useAuthStatus shares the ['account'] key (no extra request)
  // and reads isPending/data from one atomic snapshot.
  const { isLoading, account } = useAuthStatus();
  // #3412 S4 — a live in-world connection (session started AND its socket
  // connected) redirects straight into /game instead of the Hall: the Hall
  // is a menu for picking/resuming a character, not a waiting room for one
  // already in play. `active`+`isConnected` is the LIVE-connection check
  // (distinct from mere selection — see gameSlice.ts's Session doc): a
  // hydrated-but-unconnected selection (reload before reconnect) still gets
  // the Hall, since there's nothing live to jump back into yet.
  const { sessions, active } = useAppSelector((state) => state.game);
  const isLiveInWorld = !!(active && sessions[active]?.isConnected);

  useEffect(() => {
    // Resolve before forcing: while loading we don't yet know this isn't a
    // player, and the Hall must never render under forced arx (ADR-0227).
    if (isLoading || account) return;
    setForcedRealm('arx');
    return () => setForcedRealm(undefined);
  }, [setForcedRealm, isLoading, account]);

  if (isLoading) {
    return <div className="min-h-screen bg-background" aria-busy="true" />;
  }

  if (account && isLiveInWorld) {
    return <Navigate to="/game" replace />;
  }

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
