# Integration Tests

**⚠️ WARNING: These tests are NOT part of the normal test suite.**

These tests require manual setup and integration with external services. They should NEVER be run automatically in CI or as part of regular development testing.

## Purpose

Integration tests verify that our application correctly integrates with:
- Email services (Resend)
- Social authentication providers (Google, Facebook, etc.)
- External APIs and services

## Running Integration Tests

Integration tests must be run **manually** and **deliberately**. They are excluded from:
- `arx test` (normal unit test runs)
- CI/CD pipelines
- Pre-commit hooks

### Prerequisites

Before running any integration tests:

1. **Set up environment variables** in `src/.env`:
   - Email service API keys
   - Social auth provider credentials
   - ngrok URLs (for webhook testing)

2. **Review the test documentation** for specific requirements

3. **Ensure test data cleanup** - integration tests may create real data

### Running Email Verification Integration Tests

**Automated Setup + Manual Testing:**

```bash
# 1. Run automated setup (handles ngrok + environment)
arx integration-test

# 2. Follow on-screen instructions to start servers
# 3. Follow manual testing checklist in EMAIL_VERIFICATION_TESTING_GUIDE.md
# 4. Press Ctrl+C when done (auto-restores environment)
```

**Note:** First time? Add `ALLOW_INTEGRATION_TESTS=true` to `src/.env` to enable integration testing.

**Files:**
- [setup_integration_env.py](./setup_integration_env.py) - Automated environment setup
- [EMAIL_VERIFICATION_TESTING_GUIDE.md](./EMAIL_VERIFICATION_TESTING_GUIDE.md) - Testing checklist
- [manual_email_verification.py](./manual_email_verification.py) - Test checklist as Python code

**Note:** Integration test files use `manual_*.py` naming convention (NOT `test_*.py`) to prevent Django's test discovery from finding and running them automatically.

### What's Automated vs Manual

**Automated (setup command):**
- ✅ Starting/stopping ngrok tunnel
- ✅ Updating .env with ngrok URL
- ✅ Creating integration test user for authentication
- ✅ Starting Evennia backend server
- ✅ Starting frontend dev server
- ✅ Authenticating as integration user
- ✅ Registering test account via API
- ✅ **Verifying account has email_verified=false (can login, but limited actions)**
- ✅ Fetching verification email from Resend (or extracting from logs)
- ✅ Extracting verification link automatically
- ✅ **After manual click: Verifying email_verified=true**
- ✅ **Confirming user can perform full game actions**
- ✅ Configuration verification
- ✅ Environment cleanup and restoration

**Manual (human required):**
- 👤 Clicking verification link in browser
- 👤 Confirming "Email Verified!" success page displays correctly
- 👤 Pressing Enter to continue automated verification

**Note:** Unverified users CAN login, but with limited access. They can read lore but cannot create characters or play the game until verified.

## Creating New Integration Tests

When adding new integration tests:

1. **Document external dependencies** clearly
2. **Mark human-in-the-loop steps** explicitly
3. **Add cleanup procedures** to prevent test data pollution
4. **Never automate** - integration tests require manual execution
5. **Update this README** with new test instructions

## File Organization

**Naming Convention:** All integration test files use `manual_*.py` prefix to avoid Django test discovery.

- `manual_email_verification.py` - Email verification flow with Resend
- `EMAIL_VERIFICATION_TESTING_GUIDE.md` - Step-by-step testing guide
- (Future) `manual_social_auth.py` - OAuth provider integration
- (Future) `manual_password_reset.py` - Password reset email flow
