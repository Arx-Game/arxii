/**
 * Door — "How One Enters", the Gatefold's closing colophon (#3305).
 *
 * Visitor-only (#3412 slice 2): `GatefoldPage` now short-circuits an
 * authenticated account to `<HallPage/>` before this component ever mounts,
 * so the account-aware `<WelcomePanel/>` branch this component used to carry
 * is gone — Door renders the "Begin" CTA when registration is open, or a
 * quiet invite-only notice when it's closed. The motto imprint closes the
 * page unconditionally.
 */

import { Link } from 'react-router-dom';
import { useRegistrationStatus } from '@/evennia_replacements/queries';

export function Door() {
  const { data: registrationStatus } = useRegistrationStatus();
  // A slow/failed status check should never block the signup CTA — only an
  // explicit `open: false` shows the invite-only notice (mirrors RegisterPage).
  const isOpen = registrationStatus?.open ?? true;

  return (
    <div className="gatefold-colophon" id="door">
      <div className="gatefold-fleuron" aria-hidden="true">
        ❦
      </div>
      <h2>How One Enters</h2>
      {/* PLACEHOLDER: Apostate rewrite */}
      <p>
        The city takes no measure of you at the gate. Make a free account, then take up a life:
        begin your own, or claim one from the roster. The game teaches the rest as you go.
      </p>
      {isOpen ? (
        <>
          <Link to="/register" className="gatefold-btn">
            Begin
          </Link>
          <Link to="/how-to-start" className="gatefold-btn-quiet">
            or read how it works
          </Link>
        </>
      ) : (
        <>
          {/* PLACEHOLDER: Apostate rewrite */}
          <p>Registration is invite-only right now.</p>
          <Link to="/how-to-start" className="gatefold-btn-quiet">
            Read how it works
          </Link>
        </>
      )}
      <p className="gatefold-imprint">As Arx endures, we remember</p>
    </div>
  );
}
