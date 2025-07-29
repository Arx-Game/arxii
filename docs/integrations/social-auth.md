# Social Authentication Integration

Arx II uses [Django Allauth](https://django-allauth.readthedocs.io/) for social authentication, allowing players to register and login with external providers.

## Overview

Django Allauth provides comprehensive authentication with social providers. We use it for:

- Player account registration via social providers
- Secure login without password management
- Account linking and email verification
- Consistent authentication flow across web and game

## Current Configuration

### Supported Providers
- **Facebook**: Configured and ready for use
- **Google**: #TODO - Planned for future implementation
- **Discord**: #TODO - Under consideration for gaming community

### Django Settings
Configured in `src/server/conf/settings.py`:
```python
INSTALLED_APPS += [
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.facebook',
]

SOCIALACCOUNT_PROVIDERS = {
    'facebook': {
        'METHOD': 'oauth2',
        'SDK_URL': '//connect.facebook.net/{locale}/sdk.js',
        'SCOPE': ['email', 'public_profile'],
        'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
        'INIT_PARAMS': {'cookie': True},
        'FIELDS': [
            'id', 'first_name', 'last_name', 'middle_name', 'name',
            'name_format', 'picture', 'short_name'
        ],
        'EXCHANGE_TOKEN': True,
        'VERIFIED_EMAIL': False,
        'VERSION': 'v13.0',
    }
}
```

## Environment Configuration

Required environment variables in `src/.env`:

```env
# Site configuration
SITE_ID=1
SITE_DOMAIN=yoursite.org

# Facebook OAuth (when ready)
FACEBOOK_APP_ID=your_facebook_app_id
FACEBOOK_APP_SECRET=your_facebook_app_secret

# Google OAuth (future)
# GOOGLE_CLIENT_ID=your_google_client_id
# GOOGLE_CLIENT_SECRET=your_google_client_secret
```

## Implementation Status

### ✅ Completed
- Django Allauth installation and basic configuration
- Facebook provider configuration (credentials needed)
- Settings integration with proper middleware
- URL routing for auth flows
- Account model extensions via `evennia_extensions.PlayerData`

### #TODO Facebook Setup
**Next Steps for Facebook Login:**
1. Create Facebook App at [Facebook Developers](https://developers.facebook.com/)
2. Follow [Facebook Login Overview](https://developers.facebook.com/docs/facebook-login/overview)
3. Configure OAuth redirect URLs
4. Add production domain to Facebook App settings
5. Add app credentials to `.env` file
6. Test login flow in development

**Facebook App Configuration:**
- **App Type**: Consumer
- **Login Products**: Facebook Login for Web
- **Valid OAuth Redirect URIs**: `https://yoursite.org/accounts/facebook/login/callback/`
- **App Domains**: `yoursite.org`

### #TODO Google OAuth Setup
**Planned Implementation:**
1. Add `allauth.socialaccount.providers.google` to `INSTALLED_APPS`
2. Create Google Cloud Console project
3. Configure OAuth 2.0 credentials
4. Add Google provider to `SOCIALACCOUNT_PROVIDERS`
5. Test integration with Gmail accounts

## Custom User Model Integration

### Evennia AccountDB Compatibility
Arx II uses Evennia's custom user model (`accounts.AccountDB`) which extends Django's `AbstractUser`. **This works seamlessly with Django Allauth** because:

- ✅ **AccountDB extends AbstractUser**: Provides all required fields (username, email, first_name, last_name)
- ✅ **AUTH_USER_MODEL configured**: Evennia sets `AUTH_USER_MODEL = "accounts.AccountDB"`
- ✅ **Authentication backends**: Already configured for both Django and Allauth
- ✅ **No additional migration required**: AccountDB is designed for this use case

### Account Linking Strategy

### Web-First Registration
- Players register accounts via web interface
- Social auth creates Evennia AccountDB + PlayerData automatically
- No in-game registration - web accounts required for game access

### Account Management
- **Primary Identity**: Evennia AccountDB (custom user model)
- **Game Data**: `evennia_extensions.PlayerData` (extends AccountDB)
- **Character Access**: Via roster application system
- **Privacy**: Social profile data not exposed to other players

## Security Considerations

### OAuth Flow Security
- Uses secure OAuth 2.0 flows with proper state validation
- App secrets stored in environment variables only
- HTTPS required for production OAuth callbacks
- Regular token refresh for long-lived sessions

### Privacy Protection
- Social profile pictures and names not automatically public
- Player social identities not visible to other players
- Character system maintains anonymity via tenure system
- Optional: Players can unlink social accounts after registration

## Integration with Game Systems

### Character Applications
- Social auth creates base account
- Players apply for characters via web interface
- Character approval creates game access permissions
- Single account can have multiple approved characters

### Web Interface
- Social login for character gallery management
- Roster application submission and tracking
- Account settings and preferences
- Character switching interface

## Development and Testing

### Local Development
- Use Django's built-in User model
- Test OAuth flows with ngrok or similar tunneling
- Facebook/Google require HTTPS for OAuth callbacks
- Use test app credentials for development

### Production Considerations
- SSL certificate required for OAuth providers
- Production app registration with each provider
- Domain verification for Facebook/Google apps
- Rate limiting considerations for auth endpoints

## Future Enhancements

### Additional Providers (#TODO)
- **Google**: Most requested by players
- **Discord**: Popular in gaming communities
- **Steam**: Gaming-focused authentication

### Enhanced Features (#TODO)
- Account linking/unlinking interface
- Social profile import options
- Friend finding via social connections (opt-in)
- Social sharing of character achievements
- Integration with game's social systems

## Troubleshooting

### Common Issues
- **OAuth Callback Errors**: Check redirect URL configuration
- **App Secret Errors**: Verify environment variable loading
- **HTTPS Required**: Social providers require SSL in production
- **Scope Permissions**: Ensure proper OAuth scopes for email access

### Debug Settings
For development, enable detailed OAuth logging:
```python
LOGGING = {
    'loggers': {
        'allauth': {
            'level': 'DEBUG',
        },
    },
}
```
