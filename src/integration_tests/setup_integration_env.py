#!/usr/bin/env python
"""
Automated Integration Test Environment Setup

This script automates the tedious parts of integration test setup:
1. Starts ngrok tunnel automatically
2. Updates .env with ngrok URL
3. Verifies configuration
4. Provides clear human-in-the-loop instructions

Usage:
    arx integration-test
    # Or directly: python src/integration_tests/setup_integration_env.py

Note: Requires ALLOW_INTEGRATION_TESTS=true in src/.env

The command will:
- Start ngrok on port 3000
- Update FRONTEND_URL and CSRF_TRUSTED_ORIGINS in src/.env
- Print the ngrok URL for you to use
- Keep running until you Ctrl+C
- Clean up on exit

The command automatically:
- Creates integration test user (for authentication)
- Starts Evennia server (via evennia start)
- Starts frontend dev server (via pnpm dev)
- Authenticates as integration user
- Registers test account and verifies email_verified=false
- Extracts verification link (from Resend or logs)
- After manual link click, verifies email_verified=true
Note: Unverified users CAN login, but have limited access.
See EMAIL_VERIFICATION_TESTING_GUIDE.md for details.
"""

import contextlib
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: requests not installed.")
    print("Install with: uv sync")
    sys.exit(1)

try:
    from pyngrok import ngrok
    from pyngrok.conf import PyngrokConfig
except ImportError:
    print("ERROR: pyngrok not installed.")
    print("Install with: uv sync")
    sys.exit(1)


class IntegrationEnvironment:
    """Manages integration test environment setup and cleanup."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.env_file = self.project_root / "src" / ".env"
        self.env_backup = self.project_root / "src" / ".env.integration_backup"
        self.tunnel = None
        self.original_frontend_url = None
        self.original_csrf_origins = None
        self.django_process = None
        self.frontend_process = None
        self.ngrok_url = None
        self.resend_api_key = None

    def backup_env(self):
        """Backup current .env file."""
        if self.env_file.exists():
            with open(self.env_file) as f:
                content = f.read()

            with open(self.env_backup, "w") as f:
                f.write(content)

            # Parse original values for restoration
            for line in content.split("\n"):
                if line.startswith("FRONTEND_URL="):
                    self.original_frontend_url = line.split("=", 1)[1].strip()
                elif line.startswith("CSRF_TRUSTED_ORIGINS="):
                    self.original_csrf_origins = line.split("=", 1)[1].strip()

            print(f"SUCCESS: Backed up .env to {self.env_backup}")

    def start_ngrok(self, port=3000):
        """Start ngrok tunnel on specified port."""
        print(f"\nStarting Starting ngrok tunnel on port {port}...")

        try:
            # Configure ngrok
            conf = PyngrokConfig(region="us")  # Change region if needed
            self.tunnel = ngrok.connect(port, bind_tls=True, pyngrok_config=conf)

            public_url = self.tunnel.public_url
            print(f"SUCCESS: ngrok tunnel started: {public_url}")
            return public_url

        except Exception as e:
            print(f"ERROR: Failed to start ngrok: {e}")
            print(
                "\nTroubleshooting:\n"
                "1. Make sure ngrok is installed: https://ngrok.com/download\n"
                "2. You may need to sign up for a free ngrok account\n"
                "3. Run: ngrok config add-authtoken <your-token>"
            )
            sys.exit(1)

    def update_env(self, ngrok_url):
        """Update .env file with ngrok URL."""
        print("\nUpdating .env with ngrok URL...")

        if not self.env_file.exists():
            print(
                f"ERROR: .env file not found at {self.env_file}\n"
                "Please copy .env.example to .env first."
            )
            sys.exit(1)

        # Read current .env
        with open(self.env_file) as f:
            lines = f.readlines()

        # Update relevant lines
        updated_lines = []
        found_frontend_url = False
        found_csrf_origins = False

        for line in lines:
            if line.startswith("FRONTEND_URL="):
                updated_lines.append(f"FRONTEND_URL={ngrok_url}\n")
                found_frontend_url = True
            elif line.startswith("CSRF_TRUSTED_ORIGINS="):
                # Include both ngrok URL and localhost for API calls from integration script
                updated_lines.append(
                    f"CSRF_TRUSTED_ORIGINS={ngrok_url},http://localhost:4001,http://localhost:3000\n"
                )
                found_csrf_origins = True
            else:
                updated_lines.append(line)

        # Add if not found
        if not found_frontend_url:
            updated_lines.append("\n# Added by integration test setup\n")
            updated_lines.append(f"FRONTEND_URL={ngrok_url}\n")
        if not found_csrf_origins:
            updated_lines.append(
                f"CSRF_TRUSTED_ORIGINS={ngrok_url},http://localhost:4001,http://localhost:3000\n"
            )

        # Write back
        with open(self.env_file, "w") as f:
            f.writelines(updated_lines)

        print(f"SUCCESS: Updated FRONTEND_URL={ngrok_url}")
        print(
            f"SUCCESS: Updated CSRF_TRUSTED_ORIGINS={ngrok_url},http://localhost:4001,http://localhost:3000"
        )

    def restore_env(self):
        """Restore original .env file."""
        if self.env_backup.exists():
            print("\nRestoring original .env...")

            with open(self.env_backup) as f:
                content = f.read()

            with open(self.env_file, "w") as f:
                f.write(content)

            # Clean up backup
            self.env_backup.unlink()

            print("SUCCESS: Restored original .env")
        else:
            print("WARNING: No .env backup found to restore")

    def cleanup(self):
        """Clean up ngrok tunnel and restore environment."""
        print("\n\n" + "=" * 70)
        print("CLEANUP - Stopping all services")
        print("=" * 70)

        # Stop frontend
        if self.frontend_process:
            try:
                print("\nStopping frontend server...")
                self.frontend_process.terminate()
                self.frontend_process.wait(timeout=5)
                print("SUCCESS: Stopped frontend server")
            except Exception as e:
                print(f"WARNING: Failed to stop frontend: {e}")
                with contextlib.suppress(Exception):
                    self.frontend_process.kill()

        # Stop Evennia (daemon)
        if self.django_process:
            try:
                print("\nStopping Evennia server...")
                subprocess.run(
                    ["evennia", "stop"],
                    check=False,
                    cwd=self.project_root / "src",
                    timeout=10,
                )
                print("SUCCESS: Stopped Evennia server")
            except Exception as e:
                print(f"WARNING: Failed to stop Evennia: {e}")

        # Stop ngrok
        if self.tunnel:
            try:
                print("\nStopping ngrok tunnel...")
                ngrok.disconnect(self.tunnel.public_url)
                print("SUCCESS: Stopped ngrok tunnel")
            except Exception as e:
                print(f"WARNING: Failed to stop ngrok: {e}")

        with contextlib.suppress(Exception):
            ngrok.kill()

        self.restore_env()

    def start_evennia(self):
        """Start Evennia server."""
        print("\n" + "=" * 70)
        print("STARTING EVENNIA SERVER")
        print("=" * 70)
        print("Running: evennia start")
        print(f"Working directory: {self.project_root / 'src'}")

        try:
            # Use evennia start which runs as a daemon
            result = subprocess.run(
                ["evennia", "start"],
                check=False,
                cwd=self.project_root / "src",
                capture_output=True,
                text=True,
                timeout=30,
            )

            print("\n--- Evennia Output ---")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            print("--- End Output ---\n")

            if result.returncode == 0:
                print("SUCCESS: Evennia server started")
                self.django_process = True  # Mark as started (daemon, no process handle)
                return True

            print(f"ERROR: Evennia start returned exit code {result.returncode}")
            return False
        except subprocess.TimeoutExpired:
            print("ERROR: Evennia start timed out after 30 seconds")
            return False
        except FileNotFoundError:
            print("ERROR: 'evennia' command not found. Is Evennia installed?")
            print("Try: uv sync")
            return False
        except Exception as e:
            print(f"ERROR: Unexpected error starting Evennia: {e}")
            import traceback

            traceback.print_exc()
            return False

    def start_frontend(self):
        """Start frontend development server."""
        print("\n" + "=" * 70)
        print("STARTING FRONTEND SERVER")
        print("=" * 70)
        print("Running: pnpm dev")
        print(f"Working directory: {self.project_root / 'frontend'}")

        frontend_dir = self.project_root / "frontend"

        try:
            self.frontend_process = subprocess.Popen(
                ["pnpm", "dev"],
                cwd=frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                text=True,
                bufsize=1,
            )
            print("SUCCESS: Frontend process started")
            print(f"Process PID: {self.frontend_process.pid}")
            return True
        except FileNotFoundError:
            print("ERROR: 'pnpm' command not found. Is pnpm installed?")
            return False
        except Exception as e:
            print(f"ERROR: Failed to start frontend: {e}")
            import traceback

            traceback.print_exc()
            return False

    def wait_for_servers(self):
        """Wait for Evennia and frontend servers to be ready."""
        print("\n" + "=" * 70)
        print("WAITING FOR SERVERS TO BE READY")
        print("=" * 70)

        # Wait for Evennia (localhost:4001 - webserver-proxy)
        print("\nChecking Evennia backend (http://localhost:4001/api/)...")
        evennia_ready = False
        for i in range(60):  # 60 seconds max for Evennia
            try:
                response = requests.get("http://localhost:4001/api/", timeout=2)
                # 200 = OK, 404 = Not Found (but server responding), 403 = Forbidden (auth required, server ready)
                if response.status_code in [200, 403, 404]:
                    evennia_ready = True
                    print(f"SUCCESS: Evennia backend is ready (status {response.status_code})")
                    break
                print(f"Attempt {i + 1}/60: Got status {response.status_code}, waiting...")
            except requests.exceptions.ConnectionError:
                if i == 0 or (i + 1) % 10 == 0:  # Print every 10 attempts
                    print(
                        f"Attempt {i + 1}/60: Connection refused, Evennia may still be starting..."
                    )
            except requests.exceptions.Timeout:
                if i == 0 or (i + 1) % 10 == 0:
                    print(f"Attempt {i + 1}/60: Request timed out, waiting...")
            except Exception as e:
                if i == 0 or (i + 1) % 10 == 0:
                    print(f"Attempt {i + 1}/60: {type(e).__name__}: {e}")
            time.sleep(1)

        if not evennia_ready:
            print("\nWARNING: Evennia backend did not respond after 60 seconds")
            print("Possible issues:")
            print("  - Evennia may still be initializing")
            print("  - Check: evennia status")
            print("  - Check logs in: src/server/logs/server.log")

        # Wait for frontend (localhost:3000)
        print("\nChecking frontend (http://localhost:3000)...")
        frontend_ready = False
        for i in range(30):  # 30 seconds max
            try:
                response = requests.get("http://localhost:3000", timeout=2)
                if response.status_code in [200, 404]:
                    frontend_ready = True
                    print(f"SUCCESS: Frontend is ready (status {response.status_code})")
                    break
                print(f"Attempt {i + 1}/30: Got status {response.status_code}, waiting...")
            except requests.exceptions.ConnectionError:
                if i == 0 or (i + 1) % 10 == 0:
                    print(
                        f"Attempt {i + 1}/30: Connection refused, frontend may still be starting..."
                    )
            except requests.exceptions.Timeout:
                if i == 0 or (i + 1) % 10 == 0:
                    print(f"Attempt {i + 1}/30: Request timed out, waiting...")
            except Exception as e:
                if i == 0 or (i + 1) % 10 == 0:
                    print(f"Attempt {i + 1}/30: {type(e).__name__}: {e}")

            # Check if frontend process died
            if self.frontend_process and self.frontend_process.poll() is not None:
                print(
                    f"\nERROR: Frontend process died with exit code {self.frontend_process.returncode}"
                )
                print("Last output:")
                if self.frontend_process.stdout:
                    output = self.frontend_process.stdout.read()
                    print(output[-1000:] if len(output) > 1000 else output)
                break

            time.sleep(1)

        if not frontend_ready:
            print("\nWARNING: Frontend did not respond after 30 seconds")
            print("Possible issues:")
            print("  - Frontend may still be compiling")
            print("  - Check process is running")
            print("  - Port 3000 may be in use")

        print("\n" + "=" * 70)
        evennia_status = "READY" if evennia_ready else "NOT READY"
        frontend_status = "READY" if frontend_ready else "NOT READY"
        print(f"Server readiness: Evennia={evennia_status}, Frontend={frontend_status}")
        print("=" * 70)

        return evennia_ready and frontend_ready

    def ensure_integration_user(self):
        """Ensure integration test user exists, create if needed."""
        print("\n" + "=" * 70)
        print("SETTING UP INTEGRATION TEST USER")
        print("=" * 70)

        username = os.environ.get("INTEGRATION_TEST_USERNAME", "integration_test_user")
        password = os.environ.get("INTEGRATION_TEST_PASSWORD", "IntegrationTestPassword123!")
        email = os.environ.get("INTEGRATION_TEST_EMAIL", "integration_test@example.com")

        print(f"Integration user: {username}")
        print(f"Integration email: {email}")

        # Use Evennia's shell to create the user if needed
        create_user_code = f"""
from evennia.accounts.models import AccountDB
from allauth.account.models import EmailAddress

# Check if user exists
username = "{username}"
email = "{email}"
password = "{password}"

# Get or create user (idempotent)
user, created = AccountDB.objects.get_or_create(
    username=username,
    defaults={{'email': email, 'password': password}}
)

if created:
    print(f"Created integration user: {{username}}")
    # Set password properly for new users
    user.set_password(password)
    user.save()
else:
    print(f"Integration user {{username}} already exists")

# Update user's email if needed (idempotent)
if user.email != email:
    print(f"Updating user email from {{user.email}} to {{email}}")
    user.email = email
    user.save()

# Clean up any conflicting EmailAddress records
# 1. Remove this email if it's claimed by another user
other_users_email = EmailAddress.objects.filter(email=email).exclude(user=user)
if other_users_email.exists():
    count = other_users_email.count()
    print(f"Removing {{count}} EmailAddress record(s) for {{email}} claimed by other user(s)")
    other_users_email.delete()

# 2. Remove any other primary emails for this user
other_primary = EmailAddress.objects.filter(user=user, primary=True).exclude(email=email)
if other_primary.exists():
    count = other_primary.count()
    print(f"Removing {{count}} other primary email(s) for this user")
    other_primary.delete()

# 3. Remove any non-primary emails for this user (clean slate)
other_emails = EmailAddress.objects.filter(user=user).exclude(email=email)
if other_emails.exists():
    count = other_emails.count()
    print(f"Removing {{count}} other email(s) for this user")
    other_emails.delete()

# Get or create the EmailAddress we want (idempotent)
email_address, created = EmailAddress.objects.get_or_create(
    user=user,
    email=email,
    defaults={{'verified': True, 'primary': True}}
)

if created:
    print(f"Created EmailAddress: {{email}} (verified, primary)")
else:
    # Update if needed
    updated = False
    if not email_address.verified:
        email_address.verified = True
        updated = True
    if not email_address.primary:
        email_address.primary = True
        updated = True
    if updated:
        email_address.save()
        print(f"Updated EmailAddress: {{email}} (verified, primary)")
    else:
        print(f"EmailAddress already correct: {{email}} (verified, primary)")

print(f"SUCCESS: Integration user ready ({{username}}, {{email}})")
"""

        try:
            print("\nRunning: evennia shell -c <create_user_code>")
            result = subprocess.run(
                ["evennia", "shell", "-c", create_user_code],
                check=False,
                cwd=self.project_root / "src",
                capture_output=True,
                text=True,
                timeout=30,
            )

            print("\n--- Shell Output ---")
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            print("--- End Output ---\n")

            if result.returncode == 0:
                print(f"SUCCESS: Integration user {username} is ready")
                return {"username": username, "password": password, "email": email}

            print(f"ERROR: Shell command returned exit code {result.returncode}")
            return None

        except subprocess.TimeoutExpired:
            print("ERROR: Shell command timed out after 30 seconds")
            return None
        except Exception as e:
            print(f"ERROR: Failed to create integration user: {e}")
            import traceback

            traceback.print_exc()
            return None

    def authenticate_integration_user(self):
        """Authenticate integration test user and return session."""
        print("\n" + "=" * 70)
        print("AUTHENTICATING INTEGRATION USER")
        print("=" * 70)

        username = os.environ.get("INTEGRATION_TEST_USERNAME", "integration_test_user")
        password = os.environ.get("INTEGRATION_TEST_PASSWORD", "IntegrationTestPassword123!")

        print(f"Logging in as: {username}")

        try:
            # Create a session
            session = requests.Session()

            # Get CSRF token
            print("\nGetting CSRF token...")
            csrf_response = session.get("http://localhost:4001/api/auth/browser/v1/auth/login")
            csrf_token = csrf_response.cookies.get("csrftoken")

            if csrf_token:
                print(f"Got CSRF token: {csrf_token[:10]}...")
            else:
                print("WARNING: No CSRF token received")

            # Authenticate
            headers = {}
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token
                headers["Referer"] = "http://localhost:4001"

            print("\nPOST http://localhost:4001/api/auth/browser/v1/auth/login")
            response = session.post(
                "http://localhost:4001/api/auth/browser/v1/auth/login",
                json={
                    "username": username,
                    "password": password,
                },
                headers=headers,
                timeout=10,
            )

            print(f"Response status: {response.status_code}")

            if response.status_code in [200, 201]:
                print(f"SUCCESS: Authenticated as {username}")
                return session

            print(f"ERROR: Login failed with status {response.status_code}")
            print("Response body:")
            print(response.text[:500])
            return None

        except Exception as e:
            print(f"ERROR: Authentication failed: {e}")
            import traceback

            traceback.print_exc()
            return None

    def register_test_account(self, authenticated_session=None):
        """Register a test account via API.

        Args:
            authenticated_session: Authenticated requests.Session to use for API calls.
                                 If None, will create an unauthenticated session.
        """
        print("\n" + "=" * 70)
        print("REGISTERING TEST ACCOUNT")
        print("=" * 70)

        timestamp = int(time.time())
        username = f"test_integration_{timestamp}"
        email = f"test_integration_{timestamp}@example.com"
        password = "TestPassword123!"  # NOSONAR

        # Clean up any existing test account with this username/email
        print(f"\nCleaning up any existing test account: {username}")
        cleanup_code = f"""
from evennia.accounts.models import AccountDB
from allauth.account.models import EmailAddress

# Delete any existing test account with this username or email
existing_by_username = AccountDB.objects.filter(username="{username}")
existing_by_email = AccountDB.objects.filter(email="{email}")
email_addresses = EmailAddress.objects.filter(email="{email}")

if existing_by_username.exists():
    count = existing_by_username.count()
    existing_by_username.delete()
    print(f"Deleted {{count}} existing account(s) with username {username}")

if existing_by_email.exists():
    count = existing_by_email.count()
    existing_by_email.delete()
    print(f"Deleted {{count}} existing account(s) with email {email}")

if email_addresses.exists():
    count = email_addresses.count()
    email_addresses.delete()
    print(f"Deleted {{count}} EmailAddress record(s) for {email}")

print("Cleanup complete - ready for fresh registration")
"""
        try:
            result = subprocess.run(
                ["evennia", "shell", "-c", cleanup_code],
                check=False,
                cwd=self.project_root / "src",
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout:
                print(result.stdout.strip())
        except Exception as e:
            print(f"WARNING: Cleanup failed: {e}")
            print("Continuing anyway...")

        print("\nPOST http://localhost:4001/api/auth/browser/v1/auth/signup")
        print(f"Username: {username}")
        print(f"Email: {email}")

        try:
            # Use provided authenticated session or create a new one
            if authenticated_session:
                session = authenticated_session
                print("\nUsing authenticated session")
            else:
                session = requests.Session()
                print("\nCreating new unauthenticated session")

            # Get CSRF token (may already be in session if authenticated)
            print("Getting CSRF token...")
            csrf_response = session.get("http://localhost:4001/api/auth/browser/v1/auth/signup")
            csrf_token = csrf_response.cookies.get("csrftoken")

            if csrf_token:
                print(f"Got CSRF token: {csrf_token[:10]}...")
            else:
                print("WARNING: No CSRF token received")

            # Make the registration request with CSRF token
            headers = {}
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token
                headers["Referer"] = "http://localhost:4001"

            response = session.post(
                "http://localhost:4001/api/auth/browser/v1/auth/signup",
                json={
                    "username": username,
                    "email": email,
                    "password": password,
                },
                headers=headers,
                timeout=10,
            )

            print(f"Response status: {response.status_code}")
            if response.status_code == 403:
                print("ERROR: Got 403 Forbidden - CSRF or permissions issue")
                print(f"Response headers: {dict(response.headers)}")
                print(f"Response body: {response.text[:500]}")

            if response.status_code in [200, 201]:
                print("\nSUCCESS: Test account created")
                print(f"  Username: {username}")
                print(f"  Email: {email}")
                print(f"  Password: {password}")
                return {"username": username, "email": email, "password": password}

            print(f"\nERROR: Registration returned status {response.status_code}")
            print("Response body:")
            print(response.text[:500])  # Limit output
            return None

        except requests.exceptions.ConnectionError as e:
            print("\nERROR: Could not connect to Evennia backend")
            print("The server may not be running or may not have started properly")
            print(f"Details: {e}")
            return None
        except requests.exceptions.Timeout:
            print("\nERROR: Request timed out after 10 seconds")
            print("The server may be overloaded or unresponsive")
            return None
        except Exception as e:
            print(f"\nERROR: Unexpected error: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            return None

    def fetch_verification_email(self, recipient_email):
        """Fetch verification email from Resend API."""
        if not self.resend_api_key or not self.resend_api_key.startswith("re_"):
            print("\nWARNING:  RESEND_API_KEY not configured - check console output for email")
            return None

        print("\nFetching verification email from Resend...")

        try:
            # Resend API to list emails
            response = requests.get(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.resend_api_key}"},
                params={"to": recipient_email, "limit": 10},
                timeout=10,
            )

            if response.status_code != 200:
                print(f"WARNING:  Resend API returned status {response.status_code}")
                return None

            emails = response.json().get("data", [])
            if not emails:
                print(f"WARNING:  No emails found for {recipient_email}")
                return None

            # Get the most recent email
            latest_email_id = emails[0]["id"]

            # Fetch email details
            email_response = requests.get(
                f"https://api.resend.com/emails/{latest_email_id}",
                headers={"Authorization": f"Bearer {self.resend_api_key}"},
                timeout=10,
            )

            if email_response.status_code == 200:
                email_data = email_response.json()
                print("SUCCESS: Verification email found")
                return email_data
            print("WARNING:  Failed to fetch email details")
            return None

        except Exception as e:
            print(f"WARNING:  Failed to fetch email: {e}")
            return None

    def extract_verification_link(self, email_data):
        """Extract verification link from email content."""
        if not email_data:
            return None

        # Try to extract from HTML content
        html_content = email_data.get("html", "")
        text_content = email_data.get("text", "")

        # Look for verification link pattern
        pattern = r"(https?://[^\s]+/verify-email/[a-zA-Z0-9-]+)"

        # Try HTML first
        if html_content:
            match = re.search(pattern, html_content)
            if match:
                return match.group(1)

        # Try text
        if text_content:
            match = re.search(pattern, text_content)
            if match:
                return match.group(1)

        return None

    def extract_verification_link_from_logs(self, lines=500):
        """Extract verification link from Evennia server logs.

        Used as fallback when RESEND_API_KEY is not configured.
        Searches console email output in server.log for verification URLs.
        """
        print("\nSearching Evennia logs for verification link...")

        log_file = self.project_root / "src" / "server" / "logs" / "server.log"

        if not log_file.exists():
            print(f"WARNING: Log file not found: {log_file}")
            return None

        try:
            with log_file.open("r", encoding="utf-8") as f:
                # Read file from end
                content = f.read()
                all_lines = content.split("\n")
                recent_lines = all_lines[-lines:]

            # Look for verification link pattern in console email output
            pattern = r"(https?://[^\s]+/verify-email/[a-zA-Z0-9-]+)"

            for line in reversed(recent_lines):  # Start from most recent
                match = re.search(pattern, line)
                if match:
                    link = match.group(1)
                    print("SUCCESS: Found verification link in logs")
                    return link

            print("WARNING: No verification link found in recent logs")
            return None

        except Exception as e:
            print(f"WARNING: Failed to read logs: {e}")
            return None

    def verify_account_unverified(self, account_data):
        """Verify that newly registered account is in unverified state."""
        print("\n" + "=" * 70)
        print("VERIFYING ACCOUNT STATE - Should be UNVERIFIED")
        print("=" * 70)

        try:
            # Login should succeed, but email_verified should be false
            session = requests.Session()

            # Get CSRF token
            csrf_response = session.get("http://localhost:4001/api/auth/browser/v1/auth/login")
            csrf_token = csrf_response.cookies.get("csrftoken")

            headers = {}
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token
                headers["Referer"] = "http://localhost:4001"

            response = session.post(
                "http://localhost:4001/api/auth/browser/v1/auth/login",
                json={
                    "username": account_data["username"],
                    "password": account_data["password"],
                },
                headers=headers,
                timeout=10,
            )

            print(f"Login attempt status: {response.status_code}")

            if response.status_code == 200:
                print("SUCCESS: Login succeeded (users can login while unverified)")

                # Check email_verified status
                user_response = session.get(
                    "http://localhost:4001/api/accounts/me/",
                    timeout=10,
                )

                if user_response.status_code == 200:
                    user_data = user_response.json()
                    email_verified = user_data.get("email_verified", None)
                    print(f"User data: email_verified={email_verified}")

                    if email_verified is False:
                        print("SUCCESS: email_verified=false (user is in unverified state)")
                        print("Note: User can login but will be blocked from game actions")
                    elif email_verified is True:
                        print("ERROR: email_verified=true immediately after registration!")
                        print("This indicates email verification is not working correctly")
                    else:
                        print("WARNING: email_verified field not found in response")
                else:
                    print(
                        f"WARNING: Could not fetch user data (status {user_response.status_code})"
                    )
            else:
                print("ERROR: Login failed for newly registered account")
                print(f"Response: {response.text[:200]}")

        except Exception as e:
            print(f"WARNING: Could not verify account state: {e}")

    def verify_account_verified(self, account_data):
        """Verify that account became verified after clicking link."""
        print("\n" + "=" * 70)
        print("VERIFYING ACCOUNT STATE - Should be VERIFIED")
        print("=" * 70)

        try:
            session = requests.Session()

            # Get CSRF token
            csrf_response = session.get("http://localhost:4001/api/auth/browser/v1/auth/login")
            csrf_token = csrf_response.cookies.get("csrftoken")

            headers = {}
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token
                headers["Referer"] = "http://localhost:4001"

            # Login should still succeed
            response = session.post(
                "http://localhost:4001/api/auth/browser/v1/auth/login",
                json={
                    "username": account_data["username"],
                    "password": account_data["password"],
                },
                headers=headers,
                timeout=10,
            )

            print(f"Login attempt status: {response.status_code}")

            if response.status_code == 200:
                print("SUCCESS: Login succeeded after verification")

                # Check email_verified status - should now be true
                user_response = session.get(
                    "http://localhost:4001/api/accounts/me/",
                    timeout=10,
                )

                if user_response.status_code == 200:
                    user_data = user_response.json()
                    email_verified = user_data.get("email_verified", None)
                    print(f"User data: email_verified={email_verified}")

                    if email_verified is True:
                        print("SUCCESS: email_verified=true (user is now fully verified!)")
                        print("User can now perform all game actions")
                    elif email_verified is False:
                        print("ERROR: email_verified still false after clicking verification link!")
                        print("The verification flow may not be working correctly")
                    else:
                        print("WARNING: email_verified field not found in response")
                else:
                    print(
                        f"WARNING: Could not fetch user data (status {user_response.status_code})"
                    )
            else:
                print("ERROR: Login failed after verification")
                print(f"Response: {response.text[:200]}")

        except Exception as e:
            print(f"ERROR: Could not verify account state: {e}")

    def verify_configuration(self):
        """Verify that environment is properly configured."""
        print("\nChecking Checking configuration...")

        checks_passed = True

        # Check RESEND_API_KEY
        with open(self.env_file) as f:
            content = f.read()

            # Extract RESEND_API_KEY
            for line in content.split("\n"):
                if line.startswith("RESEND_API_KEY="):
                    self.resend_api_key = line.split("=", 1)[1].strip()

            if not self.resend_api_key or not self.resend_api_key.startswith("re_"):
                print("WARNING:  RESEND_API_KEY not set or invalid")
                print("   Set it in .env for email delivery testing")
                print("   Or leave it unset to use console email backend")

            if "DATABASE_URL=" not in content:
                print("ERROR: DATABASE_URL not set in .env")
                checks_passed = False

            if "SECRET_KEY=" not in content:
                print("ERROR: SECRET_KEY not set in .env")
                checks_passed = False

        return checks_passed

    def print_results(self, account_data, verification_link):
        """Print test results and next steps."""
        print("\n" + "=" * 70)
        print("INTEGRATION TEST READY - HUMAN VERIFICATION NEEDED")
        print("=" * 70)

        if account_data:
            print("\nTest Account Created:")
            print(f"  Username: {account_data['username']}")
            print(f"  Email:    {account_data['email']}")
            print(f"  Password: {account_data['password']}")

        if verification_link:
            print("\nVerification Link Found:")
            print(f"  {verification_link}")
        else:
            print("\nNo verification link found")
            if self.resend_api_key:
                print("Check Resend dashboard: https://resend.com/emails")
            print("Check Evennia logs: src/server/logs/server.log")

        print("\nTest URLs:")
        print(f"  ngrok (public):     {self.ngrok_url}")
        print("  localhost (local):  http://localhost:3000")
        print(f"  Register page:      {self.ngrok_url}/register")
        print(f"  Login page:         {self.ngrok_url}/login")

        print("\nNEXT STEPS:")
        print("  1. Click the verification link above")
        print("  2. Confirm you see 'Email Verified!' success page in your browser")
        print("  3. Return here and press Enter to verify the account state changed")

        print("\nServers Running:")
        print("  - Evennia backend:  http://localhost:4001")
        print("  - Frontend:         http://localhost:3000")
        print("  - ngrok tunnel:     " + self.ngrok_url)

        print("\nPress Ctrl+C when done to cleanup everything")
        print("=" * 70)

    def run(self):
        """Run the integration environment setup."""
        print("=" * 70)
        print("EMAIL VERIFICATION INTEGRATION TEST - AUTOMATED SETUP")
        print("=" * 70)

        # Register cleanup handler
        def signal_handler(sig, frame):
            self.cleanup()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        try:
            # Step 1: Backup .env
            self.backup_env()

            # Step 2: Start ngrok
            self.ngrok_url = self.start_ngrok(port=3000)

            # Step 3: Update .env
            self.update_env(self.ngrok_url)

            # Step 4: Verify configuration
            if not self.verify_configuration():
                print("\nConfiguration check failed. Please fix issues and try again.")
                self.cleanup()
                sys.exit(1)

            # Step 5: Start Evennia backend
            if not self.start_evennia():
                print("\nFailed to start Evennia - check if it's already running")
                self.cleanup()
                sys.exit(1)

            # Step 6: Start frontend
            if not self.start_frontend():
                print("\nFailed to start frontend - check if port 3000 is available")
                self.cleanup()
                sys.exit(1)

            # Step 7: Wait for servers
            if not self.wait_for_servers():
                print("\nServers may not be ready, but continuing anyway...")

            # Give servers a moment to fully initialize
            time.sleep(2)

            # Step 8: Ensure integration user exists
            integration_user = self.ensure_integration_user()
            if not integration_user:
                print("\nFailed to create integration user - check logs above")
                self.cleanup()
                sys.exit(1)

            # Step 9: Authenticate as integration user
            authenticated_session = self.authenticate_integration_user()
            if not authenticated_session:
                print("\nFailed to authenticate integration user - check logs above")
                self.cleanup()
                sys.exit(1)

            # Step 10: Register test account (using authenticated session)
            account_data = self.register_test_account(authenticated_session)

            # Step 11: Verify account is in unverified state
            if account_data:
                self.verify_account_unverified(account_data)

            # Step 12: Fetch verification email or extract from logs
            verification_link = None
            if account_data:
                if self.resend_api_key:
                    # Wait a moment for email to be sent
                    time.sleep(3)
                    email_data = self.fetch_verification_email(account_data["email"])
                    verification_link = self.extract_verification_link(email_data)
                else:
                    # Fallback: extract from console email logs
                    time.sleep(2)  # Give console email time to be logged
                    verification_link = self.extract_verification_link_from_logs()

            # Step 13: Print results and wait for manual verification
            self.print_results(account_data, verification_link)

            # Step 14: Wait for user to complete manual steps
            if account_data and verification_link:
                try:
                    print("\n" + "=" * 70)
                    input(
                        "Press Enter after you've clicked the verification link and seen the success page..."
                    )
                    print("=" * 70)

                    # Step 15: Verify account is now in verified state
                    self.verify_account_verified(account_data)
                except KeyboardInterrupt:
                    pass  # Cleanup handled by signal handler

            # Keep running (cross-platform compatible)
            print("\n" + "=" * 70)
            print("INTEGRATION TEST COMPLETE")
            print("=" * 70)
            print("\nPress Ctrl+C to cleanup and exit")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass  # Cleanup handled by signal handler

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback

            traceback.print_exc()
            self.cleanup()
            sys.exit(1)


def main():
    """Main entry point."""
    env = IntegrationEnvironment()
    env.run()


if __name__ == "__main__":
    main()
