# Email Integration

Arx II uses [SendGrid](https://sendgrid.com/) for transactional email delivery, handling roster application notifications and password resets.

## Overview

SendGrid provides reliable email delivery services. We use it for:

- Roster application confirmations and notifications
- Application approval/denial emails to players
- Staff notifications for new applications
- Password reset emails with secure tokens
- Automated workflow communications

## Configuration

Required environment variables in `src/.env`:

```env
SENDGRID_API_KEY=your_sendgrid_api_key
DEFAULT_FROM_EMAIL=noreply@yoursite.org
SITE_DOMAIN=yoursite.org
```

Optional staff notification settings:
```env
STAFF_NOTIFICATION_EMAILS=admin1@yoursite.org,admin2@yoursite.org
```

## Implementation Details

### Service Layer
- **Location**: `src/world/roster/email_service.py`
- **Class**: `RosterEmailService`
- **Key Methods**:
  - `send_application_confirmation()` - Player receives application confirmation
  - `send_application_approved()` - Approval notification with character details
  - `send_application_denied()` - Denial notification with optional reason
  - `send_staff_application_notification()` - Alert staff to new applications
  - `send_password_reset_email()` - Secure password reset with Django tokens

### Django Integration
- **Backend**: `django-sendgrid-v5` configured in `settings.py`
- **Templates**: HTML and plain text versions in `templates/roster/email/`
- **Security**: Uses Django's built-in token system for password resets

### Email Templates
Templates are located in `src/templates/roster/email/`:
- `application_confirmation.html` - Application receipt confirmation
- `application_approved.html` - Approval notification
- `application_denied.html` - Rejection notification  
- `staff_notification.html` - Staff alert for new applications
- `password_reset.html` - Secure password reset link

### Automatic Triggers
Emails are automatically sent via Django signals:
- **Application Created**: Confirmation to player, notification to staff
- **Application Approved**: Success notification to player
- **Application Denied**: Update notification to player

## Security Features

- **Token-based Password Resets**: Uses Django's secure token generator
- **Rate Limiting**: SendGrid provides built-in rate limiting
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
- Retry logic for transient failures
- Fallback to admin email list if staff emails not configured

## Testing and Development

For development environments:
- Set `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` in settings
- Emails will be printed to console instead of sent
- Test with small staff email lists to avoid spam during development

## Monitoring and Maintenance

- Monitor SendGrid dashboard for delivery rates and bounces
- Review email logs for failed deliveries
- Update email templates as game features evolve
- Maintain staff notification email lists

## Future Enhancements

- Email preferences per player (digest vs immediate)
- Rich HTML email templates with game theming
- Integration with in-game mail system
- Scheduled digest emails for staff
- Player communication preferences dashboard
