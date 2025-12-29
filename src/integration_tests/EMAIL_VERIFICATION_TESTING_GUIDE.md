# Email Verification Integration Testing Guide

**⚠️ MANUAL TESTING REQUIRED (but mostly automated!)**

This guide covers testing the email verification flow with real services. Most setup is now automated!

## Quick Start (Automated)

```bash
# 1. Run automated setup (handles ngrok + .env)
arx integration-test

# 2. In separate terminals, start servers (command will tell you)
# Terminal 2: uv run arx manage runserver
# Terminal 3: cd frontend && pnpm dev

# 3. Follow human-in-the-loop steps below
```

**Note:** First time? Add `ALLOW_INTEGRATION_TESTS=true` to `src/.env`

**That's it!** The command handles ngrok tunnel, .env updates, and cleanup.

## Quick Reference

**Services Needed:** Resend account (or console output)
**Tools Needed:** ~~ngrok~~ Automated!
**Time Required:** ~10-15 minutes

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] Python dependencies installed: `uv sync`
- [ ] Resend API key (get from https://resend.com/api-keys)
- [ ] ngrok installed (`ngrok version` to check)
- [ ] Test email address you can access
- [ ] Environment configured in `src/.env`
- [ ] Database migrated (`uv run arx manage migrate`)

## Part 1: Environment Setup (Automated!)

### Step 1: Run Automated Setup Command

```bash
# This handles everything: ngrok tunnel, .env updates, configuration checks
arx integration-test
```

**The command will:**
- ✅ Start ngrok tunnel automatically
- ✅ Backup your current .env
- ✅ Update FRONTEND_URL and CSRF_TRUSTED_ORIGINS
- ✅ Print the ngrok URL
- ✅ Show you what to do next
- ✅ Keep running (maintaining tunnel)
- ✅ Restore .env on Ctrl+C

**Optional Manual Configuration:**

If not using Resend, edit `src/.env` before running the command:
```bash
# Leave empty to use console email backend (prints to terminal)
RESEND_API_KEY=

# Or add your Resend API key
RESEND_API_KEY=re_your_actual_api_key_here
DEFAULT_FROM_EMAIL=onboarding@resend.dev
```

### Step 2: Start Servers (In New Terminals)

**Terminal 1:** Integration setup command (already running)

**Terminal 2:** Django backend
```bash
cd src
uv run arx manage runserver
```

**Terminal 3:** React frontend
```bash
cd frontend
pnpm dev
```

**Verify servers are running:**
- [ ] Backend: http://localhost:8000/admin/ loads
- [ ] Frontend: http://localhost:3000/ loads
- [ ] ngrok URL (from script output) loads

## Part 2: Registration Flow

### Step 4: Register New Account

**HUMAN ACTION REQUIRED**

1. Open browser to: https://abc123.ngrok-free.app/register
2. Fill registration form:
   - Username: `test_email_verify_<your_name>`
   - Email: **USE YOUR REAL EMAIL** (you need to check it)
   - Password: `TestPass123!`
   - Confirm: `TestPass123!`
3. Click "Register"

**Expected Result:**
- [ ] Redirected to `/register/verify-email`
- [ ] See "Check Your Email" page
- [ ] See bullet points: "Check your email inbox", "Click the verification link", etc.
- [ ] See "Resend Verification Email" button

### Step 5: Check Email Was Sent

**HUMAN ACTION REQUIRED**

**Option A: Using Resend (recommended)**
1. Go to https://resend.com/emails
2. Find the most recent email
3. Click to view details
4. Verify:
   - [ ] Recipient is your email
   - [ ] Subject mentions email verification
   - [ ] Status is "Delivered" or "Sent"
   - [ ] Email contains verification link

**Option B: Using Console Backend (no Resend key)**
1. Check Terminal 2 (Django runserver output)
2. Find email output in console
3. Copy the verification link

**Option C: Check Your Inbox**
1. Open your email inbox
2. Look for email from Arx II / your configured sender
3. Check spam folder if not in inbox

## Part 3: Email Verification

### Step 6: Click Verification Link

**HUMAN ACTION REQUIRED**

1. **Copy verification link from email**
   - Should look like: `https://abc123.ngrok-free.app/verify-email/abc123def456...`
2. **Click the link or paste into browser**

**Expected Result:**
- [ ] See spinner: "Verifying Your Email"
- [ ] See success: "Email Verified!" with green checkmark
- [ ] See "Continue to Login" button
- [ ] Auto-redirect to `/login` after 2 seconds

### Step 7: Verify Database State

**HUMAN ACTION REQUIRED**

```bash
# Terminal 4: Django shell
uv run arx shell
```

```python
# In Django shell
from allauth.account.models import EmailAddress
from evennia.accounts.models import AccountDB

# Replace with your test username
email_addr = EmailAddress.objects.get(user__username='test_email_verify_yourname')
print(f"Email: {email_addr.email}")
print(f"Verified: {email_addr.verified}")  # Should be True
print(f"Primary: {email_addr.primary}")    # Should be True

# Exit shell
exit()
```

**Expected Output:**
- [ ] `Verified: True`
- [ ] `Primary: True`

## Part 4: Login After Verification

### Step 8: Test Login

**HUMAN ACTION REQUIRED**

1. If not auto-redirected, go to: https://abc123.ngrok-free.app/login
2. Enter credentials:
   - Username: `test_email_verify_<your_name>`
   - Password: `TestPass123!`
3. Click "Login"

**Expected Result:**
- [ ] Login succeeds
- [ ] Redirected to home page (`/`)
- [ ] See username in navigation/header
- [ ] No verification warnings or errors

## Part 5: Resend Email Feature

### Step 9: Test Resend Verification

**HUMAN ACTION REQUIRED**

1. Create a second test account (repeat Step 4 with different username)
2. On "Check Your Email" page: https://abc123.ngrok-free.app/register/verify-email
3. Click "Resend Verification Email" button

**Expected Result:**
- [ ] Button shows "Sending..." briefly
- [ ] Success message appears: "✓ Verification email resent successfully!"
- [ ] New email received (check Resend dashboard or inbox)
- [ ] New verification link works

## Part 6: Error Cases

### Step 10: Test Invalid Verification Key

**HUMAN ACTION REQUIRED**

1. Navigate to: https://abc123.ngrok-free.app/verify-email/invalid-key-123
2. Observe the error page

**Expected Result:**
- [ ] See "Verification Failed" with red X icon
- [ ] Error message: "Invalid email confirmation key"
- [ ] "Resend Verification Email" button present
- [ ] "Back to Registration" link present

### Step 11: Test Expired Key

**HUMAN ACTION REQUIRED**

```bash
# Terminal 4: Django shell
uv run arx shell
```

```python
# In Django shell - expire the most recent confirmation
from allauth.account.models import EmailConfirmation
from django.utils import timezone
import datetime

conf = EmailConfirmation.objects.latest('created')
print(f"Expiring key: {conf.key[:10]}...")
conf.sent = timezone.now() - datetime.timedelta(days=4)
conf.save()
exit()
```

1. Click the verification link from that email

**Expected Result:**
- [ ] See "Verification Failed"
- [ ] Error message mentions "expired"

### Step 12: Test Login with Unverified Account

**HUMAN ACTION REQUIRED**

1. Create new account (don't verify)
2. Attempt to log in immediately

**Expected Result:**
- [ ] Login blocked
- [ ] Error indicates email verification required

## Part 7: Cleanup

### Step 13: Clean Up Test Data

**HUMAN ACTION REQUIRED**

```bash
# Terminal 4: Django shell
uv run arx shell
```

```python
# Delete all test accounts
from evennia.accounts.models import AccountDB
AccountDB.objects.filter(username__startswith='test_email_verify_').delete()
exit()
```

### Step 14: Stop Services & Cleanup

**AUTOMATED CLEANUP:**

1. Stop Django (Terminal 2): Ctrl+C
2. Stop Frontend (Terminal 3): Ctrl+C
3. **Stop integration command (Terminal 1): Ctrl+C**

When you press Ctrl+C on the integration command, it will:
- ✅ Stop the ngrok tunnel
- ✅ Restore your original .env file
- ✅ Clean up backup files

**That's it!** Your environment is back to normal.

## Automated Configuration Tests

You can run these automated tests to verify config without manual steps:

```bash
# These only check configuration, not the full flow
# Note: Must specify full path since files don't use test_*.py naming
python src/manage.py test integration_tests.manual_email_verification.EmailConfigurationTest
```

## Troubleshooting

### Email Not Received

1. **Check Resend Dashboard** - is email showing as sent?
2. **Check spam folder** - verification emails often go to spam
3. **Verify sender email** - some providers block certain senders
4. **Check Resend API limits** - free tier has sending limits
5. **Try console backend** - set `RESEND_API_KEY=` (empty) to use console output

### ngrok URL Not Working

1. **Check ngrok is running** - should show "Session Status: online"
2. **Verify FRONTEND_URL** matches ngrok URL exactly
3. **Restart Django server** after changing .env
4. **Check CSRF_TRUSTED_ORIGINS** includes the ngrok URL
5. **Try incognito window** - clear browser cache issues

### Verification Link Broken

1. **Check link format** - should be `/verify-email/{key}`
2. **Verify frontend route** exists in App.tsx
3. **Check browser console** for JavaScript errors
4. **Verify API endpoint** is accessible: curl to `/api/auth/browser/v1/auth/email/verify`

### "Database not set up" Errors

```bash
# Run migrations
uv run arx manage migrate

# Verify tables exist
uv run arx shell
```

```python
from allauth.account.models import EmailAddress
EmailAddress.objects.count()  # Should not error
```

## Success Criteria

After completing this guide, you should have verified:

- [x] Users can register new accounts
- [x] Verification emails are sent via Resend
- [x] Verification links work correctly
- [x] Email addresses are marked as verified in database
- [x] Verified users can log in
- [x] Unverified users cannot log in
- [x] Resend verification button works
- [x] Invalid/expired keys show appropriate errors
- [x] All test data cleaned up

## Next Steps

Once email verification is confirmed working:

1. **Password Reset** - implement and test similar flow
2. **Social Auth** - add OAuth providers (Google, Discord)
3. **Production Deployment** - update .env for production domain
4. **Monitoring** - set up email delivery monitoring in Resend
