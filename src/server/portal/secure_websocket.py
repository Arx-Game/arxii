"""
Secure WebSocket client for Evennia that reads session from HTTP cookies.

This implementation provides better security than the default approach by:
- Reading session IDs from HttpOnly cookies instead of URL parameters
- Preventing XSS attacks that could steal session information
- Maintaining full compatibility with Evennia's authentication system

See src/web/WEBCLIENT_METADATA.md for future expansion ideas.
"""

from evennia.server.portal.webclient import WebSocketClient


class SecureWebSocketClient(WebSocketClient):
    """
    WebSocket client that authenticates using secure HTTP cookies.

    Instead of requiring session IDs to be passed in URL parameters (where they
    could be accessed by JavaScript), this client reads the session from HTTP
    cookies sent during the websocket handshake. This allows session cookies
    to remain HttpOnly for better XSS protection.
    """

    def get_client_session(self):
        """
        Override to get the session from cookies instead of URL parameters.

        The default implementation reads session from URL query parameters, but this
        exposes session IDs to JavaScript. Instead, we read from HTTP cookies which
        can be HttpOnly and thus protected from XSS attacks.

        Returns:
            csession (ClientSession): Django session object or None.
        """
        try:
            # Access HTTP headers from the websocket handshake
            cookie_header = self.http_headers.get("cookie", "")

            if not cookie_header:
                self.csessid = None
                return None

            # Parse cookies to find sessionid
            cookies = {}
            for cookie_pair in cookie_header.split(";"):
                cookie_pair = cookie_pair.strip()
                if "=" in cookie_pair:
                    name, value = cookie_pair.split("=", 1)
                    cookies[name.strip()] = value.strip()

            sessionid = cookies.get("sessionid")
            if not sessionid:
                self.csessid = None
                return None

            # Set session ID for compatibility with parent class
            self.csessid = sessionid

            # Detect browser type from User-Agent header (same logic as Evennia's
            # webclient)
            self.browserstr = self._detect_browser_type()

            # Return Django session object
            from django.conf import settings
            from evennia.utils import mod_import

            _CLIENT_SESSIONS = mod_import(settings.SESSION_ENGINE).SessionStore
            return _CLIENT_SESSIONS(session_key=sessionid)

        except Exception as e:
            from evennia.utils import logger

            logger.log_err(
                f"SecureWebSocketClient: Error reading session from cookies: {e}",
            )
            self.csessid = None
            return None

    def at_login(self):
        """
        Called when this session successfully logs in.
        Store the UID in the browser session for future autologin.
        """
        csession = self.get_client_session()
        if csession:
            # Store UID (like parent) and nonce (which parent doesn't do)
            csession["webclient_authenticated_uid"] = self.uid
            self.nonce = getattr(self, "nonce", 0) + 1
            csession["webclient_authenticated_nonce"] = self.nonce
            csession.save()

    def disconnect(self, reason=None):
        """
        Override disconnect to handle session cleanup properly.
        Only clear the webclient session if this is the last session for the account.
        """
        csession = self.get_client_session()

        if csession:
            current_nonce = csession.get("webclient_authenticated_nonce", 0)

            # Check if this account has other active sessions
            active_sessions = 0
            if hasattr(self, "uid") and self.uid:
                # Count sessions with the same csessid (browser session)
                try:
                    csessid = self.csessid
                    same_csession_count = len(
                        [
                            s
                            for s in self.sessionhandler.sessions_from_csessid(csessid)
                            if s != self
                        ],
                    )
                    active_sessions = same_csession_count + 1  # +1 for current session
                except Exception:
                    # Fallback: always preserve session to be safe
                    active_sessions = 2

            # Only clear webclient auth if this is the last session AND nonce matches
            if current_nonce == self.nonce and active_sessions <= 1:
                # Let parent handle the standard cleanup
                super().disconnect(reason)
            else:
                # Don't clear the session, but still disconnect
                self.logged_in = False
                self.sessionhandler.disconnect(self)
                from evennia.server.portal.webclient import CLOSE_NORMAL

                self.sendClose(CLOSE_NORMAL, reason)
        else:
            # No session, use parent logic
            super().disconnect(reason)

    def _detect_browser_type(self):
        """
        Detect browser type from User-Agent header.
        Uses the same logic as Evennia's webclient JavaScript implementation.
        """
        user_agent = self.http_headers.get("user-agent", "").lower()

        browser_markers = [
            ("edge", "edge"),
            ("edg", "chromium based edge (dev or canary)"),
            ("opr", "opera"),
            ("chrome", "chrome"),
            ("trident", "ie"),
            ("firefox", "firefox"),
            ("safari", "safari"),
        ]
        for marker, name in browser_markers:
            if marker in user_agent:
                return name
        return "other"
