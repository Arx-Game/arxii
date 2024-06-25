"""
These exceptions are raised when players try to execute some action. Methods that are
called by commands or from the website should raise one of these exceptions whenever
the action should be blocked.
"""


class CommandError(Exception):
    def __init__(self, msg, details=None):
        self.msg = msg
        self.details = details
