"""Tests for the Resend HTTPS API email backend.

Production blocked outbound SMTP (587/465) at the provider level, so the SMTP
backend against smtp.resend.com timed out and turned every signup into an HTTP
500 (see ADR-0216). These tests pin ResendAPIEmailBackend's contract: it must
never make a real network call in a test, so requests.post is mocked
throughout.
"""

from unittest.mock import MagicMock, patch

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import TestCase, override_settings
import requests

from world.roster.email_backend import (
    RESEND_API_URL,
    ResendAPIEmailBackend,
    ResendAttachmentsNotSupportedError,
)

TARGET = "world.roster.email_backend.requests.post"


def _mock_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    return response


@override_settings(RESEND_API_KEY="re_test_key")
class ResendAPIEmailBackendTests(TestCase):
    def test_plain_text_message_is_sent(self):
        message = EmailMessage(
            subject="Hello",
            body="Plain body",
            from_email="noreply@arx2.com",
            to=["player@example.com"],
        )
        backend = ResendAPIEmailBackend()

        with patch(TARGET, return_value=_mock_response()) as post:
            sent_count = backend.send_messages([message])

        self.assertEqual(sent_count, 1)
        post.assert_called_once()
        _args, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["from"], "noreply@arx2.com")
        self.assertEqual(kwargs["json"]["to"], ["player@example.com"])
        self.assertEqual(kwargs["json"]["subject"], "Hello")
        self.assertEqual(kwargs["json"]["text"], "Plain body")
        self.assertNotIn("html", kwargs["json"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer re_test_key")
        self.assertIn("timeout", kwargs)
        self.assertEqual(post.call_args.args[0], RESEND_API_URL)

    def test_html_alternative_is_sent_as_html(self):
        message = EmailMultiAlternatives(
            subject="Hello HTML",
            body="Plain fallback",
            from_email="noreply@arx2.com",
            to=["player@example.com"],
        )
        message.attach_alternative("<p>Hi</p>", "text/html")
        backend = ResendAPIEmailBackend()

        with patch(TARGET, return_value=_mock_response()) as post:
            backend.send_messages([message])

        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["json"]["text"], "Plain fallback")
        self.assertEqual(kwargs["json"]["html"], "<p>Hi</p>")

    def test_multiple_recipients_cc_bcc_and_reply_to(self):
        message = EmailMessage(
            subject="Multi",
            body="Body",
            from_email="noreply@arx2.com",
            to=["one@example.com", "two@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            reply_to=["reply@example.com"],
        )
        backend = ResendAPIEmailBackend()

        with patch(TARGET, return_value=_mock_response()) as post:
            backend.send_messages([message])

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["to"], ["one@example.com", "two@example.com"])
        self.assertEqual(payload["cc"], ["cc@example.com"])
        self.assertEqual(payload["bcc"], ["bcc@example.com"])
        self.assertEqual(payload["reply_to"], ["reply@example.com"])

    def test_fail_silently_true_swallows_provider_error_and_returns_zero(self):
        message = EmailMessage(
            subject="Will fail",
            body="Body",
            from_email="noreply@arx2.com",
            to=["player@example.com"],
        )
        backend = ResendAPIEmailBackend(fail_silently=True)

        with patch(TARGET, side_effect=requests.exceptions.ConnectTimeout("timed out")):
            sent_count = backend.send_messages([message])

        self.assertEqual(sent_count, 0)

    def test_fail_silently_false_raises(self):
        message = EmailMessage(
            subject="Will fail",
            body="Body",
            from_email="noreply@arx2.com",
            to=["player@example.com"],
        )
        backend = ResendAPIEmailBackend(fail_silently=False)

        with patch(TARGET, side_effect=requests.exceptions.ConnectTimeout("timed out")):
            with self.assertRaises(requests.exceptions.ConnectTimeout):
                backend.send_messages([message])

    def test_returns_count_of_successfully_sent_messages(self):
        messages = [
            EmailMessage(
                subject=f"Message {i}",
                body="Body",
                from_email="noreply@arx2.com",
                to=["player@example.com"],
            )
            for i in range(3)
        ]
        backend = ResendAPIEmailBackend()

        with patch(TARGET, return_value=_mock_response()) as post:
            sent_count = backend.send_messages(messages)

        self.assertEqual(sent_count, 3)
        self.assertEqual(post.call_count, 3)

    def test_empty_message_list_returns_zero_without_calling_out(self):
        backend = ResendAPIEmailBackend()

        with patch(TARGET) as post:
            sent_count = backend.send_messages([])

        self.assertEqual(sent_count, 0)
        post.assert_not_called()

    def test_attachments_raise_a_typed_error(self):
        message = EmailMessage(
            subject="Has attachment",
            body="Body",
            from_email="noreply@arx2.com",
            to=["player@example.com"],
        )
        message.attach("notes.txt", "some content", "text/plain")
        backend = ResendAPIEmailBackend(fail_silently=False)

        with patch(TARGET) as post:
            with self.assertRaises(ResendAttachmentsNotSupportedError):
                backend.send_messages([message])

        post.assert_not_called()

    def test_http_error_status_is_treated_as_a_failed_send(self):
        message = EmailMessage(
            subject="Rejected",
            body="Body",
            from_email="noreply@arx2.com",
            to=["player@example.com"],
        )
        response = MagicMock()
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("422")
        backend = ResendAPIEmailBackend(fail_silently=True)

        with patch(TARGET, return_value=response):
            sent_count = backend.send_messages([message])

        self.assertEqual(sent_count, 0)
