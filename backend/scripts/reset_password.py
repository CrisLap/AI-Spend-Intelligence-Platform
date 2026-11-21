"""Reset a single user's password without touching any other data.

Usage:
    cd backend
    python scripts/reset_password.py                      # admin demo account, prompts for password
    python scripts/reset_password.py --email someone@x.io # any other user

The new password is read from the RESET_PASSWORD env var if set, otherwise
prompted for interactively (not echoed, so it stays out of shell history).
Minimum length matches UserCreate.password (10 characters).

Requires DATABASE_URL to be reachable (same as the running app). If the API
is running, restart it afterwards to clear any in-memory login lockout
(core/login_throttle.py) left by earlier failed attempts.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user import User  # noqa: E402

DEFAULT_EMAIL = "demo.admin@spendintel.io"
MIN_LENGTH = 10
MAX_LENGTH = 128


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a user's password")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help=f"default: {DEFAULT_EMAIL}")
    args = parser.parse_args()

    password = os.environ.get("RESET_PASSWORD")
    if not password:
        password = getpass.getpass("New password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.")
            return 1

    if not (MIN_LENGTH <= len(password) <= MAX_LENGTH):
        print(f"Password must be {MIN_LENGTH}-{MAX_LENGTH} characters.")
        return 1

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        if user is None:
            print(f"No user found with email {args.email}.")
            return 1
        user.hashed_password = hash_password(password)
        db.commit()
        print(f"Password updated for {user.email} (role: {user.role}).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
