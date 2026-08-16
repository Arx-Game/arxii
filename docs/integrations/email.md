# Email Integration

Arx II uses [Resend](https://resend.com/) for transactional email delivery, handling
roster application notifications, registration invites, character-creation review
notices, and allauth's own verification / password-reset mail.

## Overview

Resend provides transactional email delivery. We use it for:

- Roster application confirmations and notifications
- Application approval/denial emails to players
- Staff notifications for new applications
- Account invites and password reset emails
- allauth's account-verification mail

## Configuration

Required environment variables in `src/.env`:

```env
RESEND_API_KEY=re_your-resend-api-key
DEFAULT_FROM_EMAIL=noreply@arx2.com
SITE_URL=https://arx2.com
```

`DEFAULT_FROM_EMAIL` must be an address on a domain Resend has verified for sending —
Resend rejects a send whose From domain it does not recognize. `arx2.com` is the
verified sending domain in production.

Optional staff notification settings:
```env
STAFF_NOTIFICATION_EMAILS=admin1@yoursite.org,admin2@yoursite.org
```

## Implementation Details

### Transport: Resend's HTTPS API, not SMTP

`world.roster.email_backend.ResendAPIEmailBackend` sends mail with a
`POST https://api.resend.com/emails` HTTPS call (short, explicit timeout), not an
SMTP connection. `settings.py` wires it in as `EMAIL_BACKEND` whenever
`RESEND_API_KEY` is set and `DEBUG` is off:

```python
EMAIL_BACKEND = "world.roster.email_backend.ResendAPIEmailBackend"
```

Production's outbound SMTP (ports 587 and 465) is blocked at the provider level,
which used to turn every signup into an HTTP 500 (the SMTP socket connect timed
out mid-request). Port 443 to `api.resend.com` is open, so the HTTPS API call
never hits that block. See ADR-0216 for the full rationale.

The backend does not send attachments — it raises
`ResendAttachmentsNotSupportedError` rather than silently dropping a file, since no
caller in this codebase sends one today.

### Service Layer
- **Location**: `src/world/roster/email_service.py`
- **Class**: `EmailServiceBase` (shared `_send_email`/`_get_staff_emails`
  primitives), subclassed by `RosterEmailService`
  (`send_application_confirmation()`, `send_application_approved()`,
  `send_application_denied()`, `send_staff_application_notification()`,
  `send_password_reset_email()`)
- **Sibling domain services**: `world.registration.email_service.RegistrationEmailService`
  (account invites) and `world.character_creation.email_service.CGEmailService`
  (application review) both subclass `EmailServiceBase` directly rather than
  `RosterEmailService`, to avoid inheriting its roster-specific method signatures.

### Django Integration
- **Backend**: `world.roster.email_backend.ResendAPIEmailBackend`, configured in
  `settings.py`
- **Templates**: HTML and plain text versions in `templates/roster/email/`
- **Security**: Uses Django's built-in token system for password resets

### Email Templates
Templates are located in `src/templates/roster/email/`:
- `application_confirmation.html` - Application receipt confirmation
- `application_approved.html` - Approval notification
- `application_denied.html` - Rejection notification
- `staff_notification.html` - Staff alert for new applications
- `password_reset.html` - Secure password reset link

Registration invites use `src/templates/registration/email/account_invite.html`.

### Automatic Triggers
Emails are sent via explicit service-function calls (never Django signals — see
ADR-0009):
- **Application Created**: Confirmation to player, notification to staff
- **Application Approved**: Success notification to player
- **Application Denied**: Update notification to player

## Security Features

- **Token-based Password Resets**: Uses Django's secure token generator
- **Template Escaping**: All user content is properly escaped
- **Error Handling**: Failed emails don't block application processing
- **Privacy Protection**: No sensitive game data in email content

## Staff Workflow

Staff members receive notifications containing:
- Player username (but not character associations)
- Character name and primary key
- Application text and date
- Policy review information
- Direct link to admin review interface

## Error Handling

The email service implements graceful degradation:
- Email failures are logged but don't block game operations
- Applications can be processed even if notifications fail
- Fallback to admin email list if staff emails not configured

Note: this graceful degradation is a domain-service-level choice
(`EmailServiceBase._send_email` catches and logs). It does not apply to allauth's own
signup flow, which is unrelated code and still surfaces a failed verification send as
an error to the caller — see ADR-0216 for the transport fix; whether that failure
should still fail the whole signup request is a separate, open design question.

## Testing and Development

For development environments:
- `EMAIL_BACKEND` is always `django.core.mail.backends.console.EmailBackend` in
  `DEBUG` mode (`src/server/conf/dev_settings.py`), regardless of `RESEND_API_KEY` —
  no real mail is ever sent from a dev box.
- Tests use `django.core.mail.backends.locmem.EmailBackend`
  (`src/server/conf/test_settings.py`); assert against `django.core.mail.outbox`.
- Unit tests for `ResendAPIEmailBackend` itself mock the HTTP call — see
  `src/world/roster/tests/test_email_backend.py`. Never make a real network call in a
  test.

## Monitoring and Maintenance

- Monitor the Resend dashboard for delivery rates and bounces
- Review email logs for failed deliveries
- Update email templates as game features evolve
- Maintain staff notification email lists

## Future Enhancements

- Email preferences per player (digest vs immediate)
- Rich HTML email templates with game theming
- Integration with in-game mail system
- Scheduled digest emails for staff
- Player communication preferences dashboard
