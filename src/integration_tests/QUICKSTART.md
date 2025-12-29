# Integration Testing Quick Start

Get started with integration testing in 1 command!

## One-Time Setup

```bash
# 1. Install dependencies
uv sync

# 2. Enable integration testing in src/.env
ALLOW_INTEGRATION_TESTS=true

# 3. Optional: Add Resend API key to src/.env for automated email checking
RESEND_API_KEY=re_your_api_key_here
```

## Every Time You Test

### Fully Automated (Recommended)

```bash
# Run the integration test - everything is automated!
arx integration-test
```

This command automatically:
1. Starts ngrok tunnel on port 3000
2. Updates your .env with the ngrok URL
3. Creates integration test user (for API authentication)
4. Starts Evennia backend (port 4001 - webserver-proxy)
5. Starts frontend dev server (port 3000)
6. Authenticates as integration user
7. Registers a test account via API
8. Fetches the verification email from Resend (or extracts from logs if no API key)
9. Extracts the verification link automatically
10. Shows you everything you need to manually verify
11. Cleans up everything when you press Ctrl+C

### Option 2: Manual (If you prefer control)

See [EMAIL_VERIFICATION_TESTING_GUIDE.md](./EMAIL_VERIFICATION_TESTING_GUIDE.md) for full manual instructions.

## What You'll Do

After running `arx integration-test`:

**Automated (script does this):**
- ✅ Creates integration test user for authentication
- ✅ Starts all servers
- ✅ Creates ngrok tunnel
- ✅ Authenticates with integration user
- ✅ Registers test account
- ✅ **Logs in and verifies email_verified=false (limited access)**
- ✅ Fetches verification email
- ✅ Extracts verification link
- ✅ **After you click: Logs in and verifies email_verified=true**
- ✅ **Confirms full access granted**

**Manual (you do this):**
1. Click the verification link (printed in console)
2. Confirm you see "Email Verified!" success page
3. Press Enter to continue automated checks

**Note:** Unverified users can login but have limited access (can read lore, can't create characters).

**Stop everything:**
- Press Ctrl+C once
- Script auto-cleans up everything ✨

## Human Steps (What You Actually Do)

The `arx integration-test` command handles the tedious setup. You focus on:

- ✅ **Checking email** - Verify emails are being sent
- ✅ **Clicking links** - Test the verification flow
- ✅ **Observing UI** - Make sure pages look/work correctly
- ✅ **Testing errors** - Try invalid keys, expired links, etc.

Everything else is automated!

## Troubleshooting

### "Integration tests are not enabled"
```bash
# Add to src/.env:
ALLOW_INTEGRATION_TESTS=true
```

### "Failed to start Django" or "Failed to start frontend"
- Check if ports 4001 or 3000 are already in use
- Close other Evennia/frontend instances
- Try `netstat -ano | findstr :4001` (Windows) to find what's using the port

### "ngrok not authenticated"
```bash
# Sign up at https://ngrok.com (free)
# Get your auth token
ngrok config add-authtoken YOUR_TOKEN_HERE
```

### "No verification link found"
- If using Resend: Check the API key is correct in .env
- If no Resend: Check Django console output for the email
- Resend dashboard: https://resend.com/emails

## Tips

- **Use console email backend** during development (leave RESEND_API_KEY empty)
- **Use Resend** when testing actual email delivery
- **Keep script running** - it maintains the ngrok tunnel
- **Press Ctrl+C once** when done - cleans up automatically

## Next Steps

After you've confirmed email verification works:

1. **Password reset testing** - Similar flow (not yet automated)
2. **Social auth testing** - OAuth providers (future work)
3. **Production deployment** - Remove ngrok, use real domain
