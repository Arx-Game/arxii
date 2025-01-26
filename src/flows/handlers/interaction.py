"""
For flows when a character is interacting with another character or object that
doesn't fall into the categories of moving them or attacking them.
"""

from flows.consts import EventType
from flows.handlers.base import BaseEventHandler


class ExamineEventHandler(BaseEventHandler):
    event_type = EventType.EXAMINE.value

    def execute(self):
        self.caller.do_look(self.target)
