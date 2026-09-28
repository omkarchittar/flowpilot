"""Administrative bootstrap; credentials are read securely, never passed as flags."""

import argparse
import getpass
import os

from pydantic import ValidationError
from sqlalchemy import select

from flowpilot.auth import UserCreate
from flowpilot.config import Settings
from flowpilot.db import Database
from flowpilot.models import User
from flowpilot.security import hash_password


def main():
    parser = argparse.ArgumentParser(description="Create a flowpilot account")
    parser.add_argument("command", choices=["create-user"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", default="admin")
    parser.add_argument("--password-env", help="Read password from the named environment variable")
    args = parser.parse_args()
    password = (
        os.environ.get(args.password_env, "")
        if args.password_env
        else getpass.getpass("Password (12+ characters): ")
    )
    try:
        body = UserCreate(email=args.email, name=args.name, role=args.role, password=password)
    except ValidationError:
        parser.error(
            "Invalid account details; check email, role, name and password (12–1024 characters)"
        )
    database = Database(Settings().database_url)
    try:
        with database.transaction() as db:
            if db.scalar(select(User.id).where(User.email == str(body.email))):
                parser.error("An account with that email already exists")
            row = User(
                email=str(body.email),
                name=body.name,
                role=body.role,
                password_hash=hash_password(body.password.get_secret_value()),
            )
            db.add(row)
            db.flush()
            print(f"Created {row.role} account {row.id}")
    finally:
        database.close()


if __name__ == "__main__":
    main()
