"""Interactive first administrator bootstrap; password never appears in arguments/logs."""

import asyncio
import getpass

from sqlalchemy import select

from app.company.auth import bootstrap
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.company import User


async def main():
    async with SessionLocal() as db:
        if await db.scalar(select(User.id).limit(1)):
            print("Identity store is already initialized; bootstrap is disabled.")
            return
        settings.boah_initial_admin_email = input("Initial administrator email: ").strip()
        settings.boah_initial_admin_password = getpass.getpass(
            "Password (at least 16 characters): "
        )
        confirmation = getpass.getpass("Confirm password: ")
        if confirmation != settings.boah_initial_admin_password:
            raise SystemExit("Passwords differ; no user was created.")
        try:
            await bootstrap(db)
        except ValueError:
            raise SystemExit("Invalid email or password policy; no user was created.") from None
        finally:
            settings.boah_initial_admin_password = ""
        print("Initial administrator created.")


if __name__ == "__main__":
    asyncio.run(main())
