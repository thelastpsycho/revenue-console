#!/usr/bin/env python3
"""One-time setup: creates the first operator account with every permission.

Nobody can use the admin-only Users page until at least one account exists,
so this script is the bootstrap path - run it once per environment (local,
Docker, production) after APP_SESSION_SECRET is configured. Every account
after this one is created from the Users page instead.

Usage: python backend/scripts/bootstrap_admin.py
"""
import getpass
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND_DIR / ".env")

from app.accounts import users  # noqa: E402
from app.accounts.permissions import PERMISSION_KEYS  # noqa: E402


def main():
    if users.any_users_exist():
        print('An account already exists - create additional accounts from the Users page instead.')
        sys.exit(1)

    username = input("Username: ").strip()
    display_name = input("Display name (optional, defaults to username): ").strip()
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords don't match.")
        sys.exit(1)

    try:
        user = users.create_user({
            "username": username,
            "displayName": display_name,
            "password": password,
            "permissions": sorted(PERMISSION_KEYS),
        })
    except users.ValidationError as exc:
        print(f"Could not create the account: {exc}")
        sys.exit(1)

    print(f'Created "{user["username"]}" with every permission. '
          "Log in and create the rest of your team from the Users page.")


if __name__ == "__main__":
    main()
