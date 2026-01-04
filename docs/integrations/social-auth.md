# Social Authentication Integration

Arx II uses [Django Allauth](https://django-allauth.readthedocs.io/) for social authentication, allowing players to register and login with external providers.

## Overview

Django Allauth provides comprehensive authentication with social providers. We use it for:

- Player account registration via social providers
- Secure login without password management
- Account linking and email verification
- Consistent authentication flow across web and game

## Supported Providers

All three providers are configured and ready to use once credentials are added:

| Provider | Status | Email Trusted | Notes |
|----------|--------|---------------|-------|
| Google | Ready | Yes | Recommended - most users have accounts |
| Discord | Ready | Yes | Popular in gaming communities |
| Facebook | Ready | No | Requires app review; users must verify email |

## Environment Configuration

Add credentials to `src/.env`:

```env
# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Discord OAuth
DISCORD_CLIENT_ID=your-discord-client-id
DISCORD_CLIENT_SECRET=your-discord-client-secret

# Facebook OAuth
FACEBOOK_APP_ID=your-facebook-app-id
FACEBOOK_APP_SECRET=your-facebook-app-secret
```

Only providers with valid credentials will appear in the UI.

---

## Provider Setup Guides

### Google OAuth Setup

**Developer Console**: https://console.cloud.google.com/apis/credentials

#### Setup Checklist

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Navigate to **APIs & Services > Credentials**
4. Click **Create Credentials > OAuth client ID**
5. Configure the OAuth consent screen if prompted:
   - User Type: External
   - App name, support email, developer contact
   - Scopes: `email`, `profile`, `openid`
6. Create OAuth 2.0 Client ID:
   - Application type: **Web application**
   - Name: "Arx II" (or your preference)
   - Authorized redirect URIs (see below)
7. Copy **Client ID** and **Client Secret** to `.env`

#### Redirect URIs

For local development with ngrok:
```
https://YOUR-NGROK-URL.ngrok-free.app/api/auth/browser/v1/auth/provider/callback
```

For production:
```
https://yoursite.org/api/auth/browser/v1/auth/provider/callback
```

---

### Discord OAuth Setup

**Developer Portal**: https://discord.com/developers/applications

#### Setup Checklist

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application**
3. Name your application (e.g., "Arx II")
4. Go to **OAuth2 > General**
5. Copy **Client ID** and **Client Secret** to `.env`
6. Add redirect URLs (see below)

#### Redirect URIs

Add these under **OAuth2 > General > Redirects**:

For local development with ngrok:
```
https://YOUR-NGROK-URL.ngrok-free.app/api/auth/browser/v1/auth/provider/callback
```

For production:
```
https://yoursite.org/api/auth/browser/v1/auth/provider/callback
```

---

### Facebook OAuth Setup

**Developer Console**: https://developers.facebook.com/apps/

#### Setup Checklist

1. Go to [Facebook Developers](https://developers.facebook.com/)
2. Click **Create App**
3. Select app type: **Consumer**
4. Fill in app details
5. From the dashboard, add **Facebook Login** product
6. Go to **Facebook Login > Settings**
7. Add Valid OAuth Redirect URIs (see below)
8. Go to **Settings > Basic** for App ID and App Secret
9. Copy credentials to `.env`

#### Redirect URIs

For local development with ngrok:
```
https://YOUR-NGROK-URL.ngrok-free.app/api/auth/browser/v1/auth/provider/callback
```

For production:
```
https://yoursite.org/api/auth/browser/v1/auth/provider/callback
```

#### Facebook-Specific Notes

- **Development Mode**: App works only for app admins/developers until approved
- **App Review**: Required for public use - submit for "email" permission
- **HTTPS Required**: Facebook requires HTTPS even for development
- **Business Verification**: May be required for certain features

---

## Testing with ngrok

Use `arx ngrok` to create a tunnel for OAuth callback testing.

### Quick Start

```bash
# Start ngrok tunnel (auto-updates .env files)
arx ngrok

# Check current ngrok URL
arx ngrok --status

# Force restart with new URL
arx ngrok --force
```

### Testing Workflow

1. **Start ngrok**: `arx ngrok`
2. **Note the URL**: e.g., `https://abc123.ngrok-free.app`
3. **Update provider redirect URIs** in each provider's console:
   ```
   https://abc123.ngrok-free.app/api/auth/browser/v1/auth/provider/callback
   ```
4. **Start the servers**:
   ```bash
   arx start        # Backend
   pnpm dev         # Frontend (in frontend/ directory)
   ```
5. **Test the flow**:
   - Visit `https://abc123.ngrok-free.app`
   - Click "Log in with Google/Discord/Facebook"
   - Complete OAuth flow
   - Verify redirect back to app

### Troubleshooting ngrok Testing

| Issue | Solution |
|-------|----------|
| "Redirect URI mismatch" | Update provider console with current ngrok URL |
| ngrok URL changed | Run `arx ngrok --force` and update provider consoles |
| CORS errors | Ensure `FRONTEND_URL` in `.env` matches ngrok URL |
| Cookies not set | Check browser allows third-party cookies for ngrok |

---

## Implementation Details

### Architecture

```
User clicks "Login with Google"
    ↓
Frontend calls initiateSocialLogin()
    ↓
Redirects to /api/auth/browser/v1/auth/provider/redirect
    ↓
Django Allauth redirects to Google
    ↓
User authenticates with Google
    ↓
Google redirects to /api/auth/browser/v1/auth/provider/callback
    ↓
Django Allauth creates/links account
    ↓
Redirects to frontend /auth/callback
    ↓
Frontend fetches user data and updates state
```

### Key Files

**Backend:**
- `src/server/conf/settings.py` - Provider configuration
- `src/evennia_extensions/social_adapters.py` - Custom adapter for PlayerData creation
- `src/web/api/views/general_views.py` - `SocialProvidersAPIView`

**Frontend:**
- `frontend/src/evennia_replacements/api.ts` - API functions
- `frontend/src/evennia_replacements/AuthCallbackPage.tsx` - OAuth callback handler
- `frontend/src/evennia_replacements/LoginPage.tsx` - Social login buttons
- `frontend/src/components/ConnectedAccounts.tsx` - Account linking UI

### Custom Adapter

`ArxSocialAccountAdapter` ensures PlayerData is created for social signups:

```python
class ArxSocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        PlayerData.objects.get_or_create(account=user)
        return user
```

---

## Evennia Integration

### AccountDB Compatibility

Arx II uses Evennia's custom user model (`accounts.AccountDB`) which extends Django's `AbstractUser`. This works seamlessly with Django Allauth because:

- AccountDB provides all required fields (username, email, etc.)
- `AUTH_USER_MODEL = "accounts.AccountDB"` is configured
- Authentication backends support both Django and Allauth

### Account Linking Strategy

- **Web-First Registration**: Players register via web interface
- **Automatic Setup**: Social auth creates AccountDB + PlayerData
- **Character Access**: Via roster application system
- **Privacy**: Social profile data not exposed to other players

---

## Security Considerations

### OAuth Flow Security
- Secure OAuth 2.0 flows with state validation
- App secrets in environment variables only
- HTTPS required for production callbacks

### Privacy Protection
- Social profile data not automatically public
- Player social identities not visible to others
- Players can unlink social accounts after registration

### Email Verification
- **Google**: Emails trusted as verified - no additional verification needed
- **Discord**: Emails trusted as verified - Discord requires email verification
- **Facebook**: Emails NOT trusted - users must verify email after signup
- Unverified users redirected to `/account/unverified` page

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Redirect URI mismatch" | OAuth URL doesn't match provider config | Update redirect URI in provider console |
| Provider not showing in UI | Missing or invalid credentials | Check `.env` has correct client ID/secret |
| "Access denied" error | User cancelled or app not authorized | User must approve permissions |
| Account not created | Adapter not configured | Verify `SOCIALACCOUNT_ADAPTER` in settings |
| Email verification loop | Provider email not verified | Complete email verification flow |

### Debug Logging

Enable detailed OAuth logging in settings:

```python
LOGGING = {
    'loggers': {
        'allauth': {
            'level': 'DEBUG',
        },
    },
}
```

### Checking Provider Configuration

```bash
# Start Django shell
arx shell

# Check configured providers
from allauth.socialaccount.providers import registry
print([p.id for p in registry.get_list()])

# Check if provider has credentials
from allauth.socialaccount.adapter import get_adapter
from django.test import RequestFactory
adapter = get_adapter(RequestFactory().get('/'))
# Providers without credentials won't appear in API response
```
