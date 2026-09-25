"""
Secure WebSocket client for Evennia that reads session from HTTP cookies.

This implementation provides better security than the default approach by:
- Reading session IDs from HttpOnly cookies instead of URL parameters
- Preventing XSS attacks that could steal session information
- Maintaining full compatibility with Evennia's authentication system

See src/web/WEBCLIENT_METADATA.md for future expansion ideas.
"""

import json

from django.conf import settings
from evennia.server.portal.webclient import CLOSE_NORMAL, WebSocketClient
from evennia.utils import logger, mod_import

from server.portal.diagnostics import (
    new_opaque_id,
    portal_diagnostics,
    valid_opaque_id,
)

DEFAULT_BROWSER_TYPE = "other"
DIAGNOSTIC_REGISTER = "portal_diagnostic_register"
DIAGNOSTIC_ACK = "portal_diagnostic_ack"
_DIAGNOSTIC_REGISTER_ALIASES = frozenset({DIAGNOSTIC_REGISTER, "diagnostic_register"})
_DEFAULT_REGISTRATION_LIMIT = 3
_CONTROL_FRAME_LENGTH = 3
_DATA_IN_VALUE_LENGTH = 2


class SecureWebSocketClient(WebSocketClient):
    """
    WebSocket client that authenticates using secure HTTP cookies.

    Instead of requiring session IDs to be passed in URL parameters (where they
    could be accessed by JavaScript), this client reads the session from HTTP
    cookies sent during the websocket handshake. This allows session cookies
    to remain HttpOnly for better XSS protection.
    """

    # Keepalive (#3745, ADR-0277). These are autobahn protocol options, and a
    # class attribute is the hook we have: Evennia constructs the
    # WebSocketServerFactory itself (evennia/server/portal/service.py) and never
    # calls setProtocolOptions, so the factory default of 0 - auto-ping off -
    # is what every session would otherwise get. Autobahn's _connectionMade
    # copies factory options onto each instance but skips any attribute the
    # instance already has, so the values below win. Setting them any later
    # than the handshake is too late: succeedHandshake schedules the first ping
    # before onOpen runs.
    # The N815 suppressions below stand because the camelCase is autobahn's and
    # the name IS the mechanism: `_connectionMade` looks these up by these exact
    # spellings, so renaming them to snake_case turns the keepalive off.
    autoPingInterval = settings.WEBSOCKET_AUTOPING_INTERVAL  # noqa: N815
    autoPingTimeout = settings.WEBSOCKET_AUTOPING_TIMEOUT  # noqa: N815

    def __init__(self, *args, **kwargs):
        """Initialize protocol state used by the Portal diagnostics seam."""
        super().__init__(*args, **kwargs)
        self.portal_connection_id = None
        self.portal_diagnostic_run_id = None
        self._diagnostic_registration_attempts = 0
        self._portal_local_cause = None
        self._portal_last_ping_payload = None

    @property
    def connection_id(self):
        """Return the opaque id assigned to this transport."""
        return self.portal_connection_id

    def _emit_portal_event(self, event, **fields):
        """Emit a privacy-safe structured event for this connection."""
        return portal_diagnostics.emit(
            event,
            connection_id=self.portal_connection_id,
            run_id=self.portal_diagnostic_run_id,
            **fields,
        )

    def _connectionMade(self):  # noqa: N802
        """Assign the opaque id at transport open, before the handshake callback."""
        self.portal_connection_id = new_opaque_id()
        super()._connectionMade()
        self._emit_portal_event("transport_open")

    def _registration_limit(self):
        """Return the configured registration-attempt limit."""
        value = settings.PORTAL_DIAGNOSTICS_MAX_REGISTRATION_ATTEMPTS
        return max(1, value) if isinstance(value, int) else _DEFAULT_REGISTRATION_LIMIT

    def _registration_from_frame(self, frame):
        """Extract a registration run id, or return ``None`` for an invalid frame."""
        if isinstance(frame, dict):
            frame_type = frame.get("type")
            if (
                set(frame) != {"type", "run_id"}
                or not isinstance(frame_type, str)
                or frame_type not in _DIAGNOSTIC_REGISTER_ALIASES
            ):
                return None
            return frame.get("run_id")
        if (
            not isinstance(frame, list)
            or len(frame) != _CONTROL_FRAME_LENGTH
            or frame[0] not in _DIAGNOSTIC_REGISTER_ALIASES
        ):
            return None
        args, kwargs = frame[1], frame[2]
        if isinstance(kwargs, dict) and set(kwargs) == {"run_id"} and args == []:
            return kwargs["run_id"]
        if isinstance(args, list) and len(args) == 1 and kwargs == {}:
            return args[0]
        return None

    def _is_registration_frame(self, frame):
        """Return whether a parsed frame targets the reserved Portal control."""
        if isinstance(frame, dict):
            frame_type = frame.get("type")
            return isinstance(frame_type, str) and frame_type in _DIAGNOSTIC_REGISTER_ALIASES
        return (
            isinstance(frame, list)
            and bool(frame)
            and isinstance(frame[0], str)
            and frame[0] in _DIAGNOSTIC_REGISTER_ALIASES
        )

    def _handle_diagnostic_registration(self, frame):
        """Validate and acknowledge one post-open registration frame.

        Invalid, duplicate, and rate-limited controls are consumed here and are
        never handed to ``ServerSessionHandler.data_in``.
        """
        self._diagnostic_registration_attempts += 1
        attempt = self._diagnostic_registration_attempts
        if attempt > self._registration_limit():
            self._emit_portal_event(
                "diagnostic_registration",
                cause="registration_rate_limited",
                registration_attempt=attempt,
            )
            return
        if self.portal_diagnostic_run_id is not None:
            self._emit_portal_event(
                "diagnostic_registration",
                cause="duplicate_registration",
                registration_attempt=attempt,
            )
            return
        run_id = self._registration_from_frame(frame)
        if not valid_opaque_id(run_id):
            self._emit_portal_event(
                "diagnostic_registration",
                cause="invalid_registration",
                registration_attempt=attempt,
            )
            return
        self.portal_diagnostic_run_id = run_id
        self._emit_portal_event(
            "diagnostic_registration",
            cause="registration_accepted",
            registration_attempt=attempt,
        )
        # The acknowledgement contains only the Portal id. In particular, it
        # does not echo the run id or any handshake/session data.
        self.sendLine(
            json.dumps([DIAGNOSTIC_ACK, [], {"connection_id": self.portal_connection_id}])
        )

    def onMessage(self, payload, isBinary):  # noqa: N802, N803
        """Intercept the reserved Portal registration before Evennia parsing."""
        try:
            frame = json.loads(payload.decode("utf-8"))
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
            return super().onMessage(payload, isBinary)
        if self._is_registration_frame(frame):
            self._handle_diagnostic_registration(frame)
            return None
        return super().onMessage(payload, isBinary)

    def data_in(self, **kwargs):
        """Defensively consume a direct-call registration before Server parsing."""
        for name in _DIAGNOSTIC_REGISTER_ALIASES:
            if name in kwargs:
                value = kwargs[name]
                frame = (
                    [name, value[0], value[1]]
                    if isinstance(value, list) and len(value) == _DATA_IN_VALUE_LENGTH
                    else {"type": name}
                )
                self._handle_diagnostic_registration(frame)
                return None
        return super().data_in(**kwargs)

    def onOpen(self):  # noqa: N802
        """Log websocket-open before the normal Evennia session setup."""
        self._emit_portal_event("websocket_open")
        super().onOpen()

    def onPing(self, payload):  # noqa: N802
        """Record a received protocol ping without retaining its payload."""
        self._emit_portal_event("ping_received")
        return super().onPing(payload)

    def onPong(self, payload):  # noqa: N802
        """Record a protocol pong; browser JavaScript cannot observe this."""
        matched = (
            self._portal_last_ping_payload is not None and payload == self._portal_last_ping_payload
        )
        self._emit_portal_event("auto_pong_accepted" if matched else "pong_received")
        if matched:
            self._portal_last_ping_payload = None
        return super().onPong(payload)

    def _sendAutoPing(self):  # noqa: N802
        """Record an Autobahn keepalive ping before it is sent."""
        self._emit_portal_event("auto_ping_sent")
        result = super()._sendAutoPing()
        self._portal_last_ping_payload = self.autoPingPending
        return result

    def onAutoPingTimeout(self):  # noqa: N802
        """Record keepalive timeout before Autobahn aborts the transport."""
        self._emit_portal_event("ping_timeout", category="ping_timeout", cause="abort")
        return super().onAutoPingTimeout()

    def sendClose(self, code=None, reason=None):  # noqa: N802
        """Record a local close request without recording its reason text."""
        self._portal_local_cause = self._portal_local_cause or "send_close"
        return super().sendClose(code, reason)

    def sendCloseFrame(self, code=None, reasonUtf8=None, isReply=False):  # noqa: N802, N803
        """Record a close frame sent by this protocol, redacting its reason."""
        self._emit_portal_event(
            "close_frame_sent",
            close_code=code,
            clean=code in (CLOSE_NORMAL, 1001),
            category="clean" if code in (CLOSE_NORMAL, 1001) else "transport_loss",
            cause="close_reply" if isReply else (self._portal_local_cause or "send_close"),
        )
        return super().sendCloseFrame(code, reasonUtf8, isReply)

    def onClose(self, wasClean, code=None, reason=None):  # noqa: N802, N803
        """Record the terminal close status without retaining its reason text."""
        self._emit_portal_event(
            "close_callback",
            close_code=code,
            clean=wasClean,
            category="clean" if wasClean else "transport_loss",
            cause="peer_close" if wasClean else "connection_lost",
        )
        return super().onClose(wasClean, code, reason)

    def onCloseFrame(self, code, reasonRaw):  # noqa: N802, N803
        """Record a peer close frame without retaining the raw reason."""
        self._emit_portal_event(
            "close_frame_received",
            close_code=code,
            clean=code in (CLOSE_NORMAL, 1001),
            category="clean" if code in (CLOSE_NORMAL, 1001) else "transport_loss",
            cause="peer_close",
        )
        return super().onCloseFrame(code, reasonRaw)

    def _fail_connection(self, code=1001, reason="going away"):  # noqa: ARG002
        """Record a protocol failure without logging Autobahn's reason string."""
        self._emit_portal_event(
            "protocol_fail", close_code=code, category="protocol_error", cause="fail"
        )
        return super()._fail_connection(code, "protocol failure")

    def dropConnection(self, abort=False):  # noqa: N802
        """Record a local transport drop without peer details."""
        self._emit_portal_event(
            "transport_drop", category="transport_loss", cause="abort" if abort else "send_close"
        )
        return super().dropConnection(abort)

    def connectionLost(self, reason):  # noqa: N802
        """Record transport loss; Twisted reason text is intentionally discarded."""
        self._emit_portal_event(
            "connection_lost", category="transport_loss", cause="connection_lost"
        )
        return super().connectionLost(reason)

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
                stripped_cookie = cookie_pair.strip()
                if "=" in stripped_cookie:
                    name, value = stripped_cookie.split("=", 1)
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
            _CLIENT_SESSIONS = mod_import(settings.SESSION_ENGINE).SessionStore
            return _CLIENT_SESSIONS(session_key=sessionid)

        except Exception as e:  # noqa: BLE001
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
            try:
                nonce = self.nonce
            except AttributeError:
                nonce = 0
            self.nonce = nonce + 1
            csession["webclient_authenticated_nonce"] = self.nonce
            csession.save()
        self._emit_portal_event("authenticated")

    def disconnect(self, reason=None):
        """
        Override disconnect to handle session cleanup properly.
        Only clear the webclient session if this is the last session for the account.
        """
        self._portal_local_cause = "disconnect"
        self._emit_portal_event("local_disconnect", category="clean", cause="disconnect")
        csession = self.get_client_session()

        if csession:
            current_nonce = csession.get("webclient_authenticated_nonce", 0)

            # Check if this account has other active sessions
            active_sessions = 0
            try:
                uid = self.uid
            except AttributeError:
                uid = None
            if uid:
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
                except Exception:  # noqa: BLE001 — session-count boundary
                    # Fallback: always preserve session to be safe.
                    logger.log_err("session count failed; preserving webclient session")
                    active_sessions = 2

            # Only clear webclient auth if this is the last session AND nonce matches
            if current_nonce == self.nonce and active_sessions <= 1:
                # Let parent handle the standard cleanup
                super().disconnect(reason)
            else:
                # Don't clear the session, but still disconnect
                self.logged_in = False
                self.sessionhandler.disconnect(self)

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
        return DEFAULT_BROWSER_TYPE
