"""
Secure WebSocket client for Evennia that reads session from HTTP cookies.

This implementation provides better security than the default approach by:
- Reading session IDs from HttpOnly cookies instead of URL parameters
- Preventing XSS attacks that could steal session information
- Maintaining full compatibility with Evennia's authentication system
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

            # Generate a client UID for browser identification (similar to Evennia's approach)
            import random
            import string

            self.browserstr = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=10)
            )

            # Return Django session object
            from django.conf import settings
            from evennia.utils import mod_import

            _CLIENT_SESSIONS = mod_import(settings.SESSION_ENGINE).SessionStore
            return _CLIENT_SESSIONS(session_key=sessionid)

        except Exception as e:
            from evennia.utils import logger

            logger.log_err(
                f"SecureWebSocketClient: Error reading session from cookies: {e}"
            )
            self.csessid = None
            return None
