"""Route Python ``logging`` records into Twisted's log so they reach server.log.

In production the game runs as a twistd daemon and settings.LOGGING only ever
had a StreamHandler, so every Django log line (django.request 500s, world.*
warnings, the API exception handler's traceback) reached server.log only by
accident and at the wrong level: twistd redirects the daemons' streams into
Twisted's log as ``[("stdout", info), ("stderr", error)]``, so a console
StreamHandler's INFO lands in server.log marked ``[EE]``. Evennia writes
server.log from a Twisted file observer, so re-emitting each record as a
Twisted event is the shortest path into that file at its real level (#3599).

Those accidental stderr copies are still written (each Django line appears in
server.log twice, once mislabelled) - sentry_twisted skips them by their
``log_io`` key so they cannot be reported as errors.

Every event is stamped with BRIDGE_MARKER so sentry_twisted skips it:
Sentry already captured the record through its stdlib logging integration.
"""

import logging

from twisted.logger import Logger, LogLevel

BRIDGE_MARKER = "arxii_bridged"


def _twisted_level(levelno: int) -> LogLevel:
    if levelno >= logging.CRITICAL:
        return LogLevel.critical
    if levelno >= logging.ERROR:
        return LogLevel.error
    if levelno >= logging.WARNING:
        return LogLevel.warn
    if levelno >= logging.INFO:
        return LogLevel.info
    return LogLevel.debug


class TwistedLogHandler(logging.Handler):
    """A logging.Handler that re-emits each record through twisted.logger."""

    def __init__(self, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self._loggers: dict[str, Logger] = {}

    def _logger_for(self, name: str) -> Logger:
        # Logger.emit overwrites log_namespace with the Logger's own namespace,
        # so one Logger per record name is what puts the Python logger name
        # in the [namespace] slot of the server.log line.
        logger = self._loggers.get(name)
        if logger is None:
            logger = Logger(namespace=name)
            self._loggers[name] = logger
        return logger

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
            level = _twisted_level(record.levelno)
            self._logger_for(record.name).emit(level, "{text}", text=text, **{BRIDGE_MARKER: True})
        except Exception:  # noqa: BLE001
            self.handleError(record)
