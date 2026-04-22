from django.test import TestCase

from flows.flow_stack import FlowStack, FlowStackCapExceeded


class FlowStackDepthTests(TestCase):
    def test_initial_depth(self) -> None:
        stack = FlowStack(owner=None, originating_event="attack_landed")
        self.assertEqual(stack.depth, 1)

    def test_enter_increments(self) -> None:
        stack = FlowStack(owner=None, originating_event="attack_landed")
        with stack.nested():
            self.assertEqual(stack.depth, 2)
            with stack.nested():
                self.assertEqual(stack.depth, 3)
        self.assertEqual(stack.depth, 1)

    def test_cap_enforced(self) -> None:
        stack = FlowStack(owner=None, originating_event="x", cap=2)
        with stack.nested():
            with self.assertRaises(FlowStackCapExceeded):
                with stack.nested():
                    pass

    def test_default_cap_is_eight(self) -> None:
        stack = FlowStack(owner=None, originating_event="x")
        self.assertEqual(stack.cap, 8)

    def test_was_cancelled_reflects_flag(self) -> None:
        stack = FlowStack(owner=None, originating_event="x")
        self.assertFalse(stack.was_cancelled())
        stack.mark_cancelled()
        self.assertTrue(stack.was_cancelled())
