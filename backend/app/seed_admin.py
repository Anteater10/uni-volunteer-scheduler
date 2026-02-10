import os

from app.database import SessionLocal
from app import models
from app.deps import hash_password


def main():
    db = SessionLocal()
    try:
        email = os.getenv("SEED_ADMIN_EMAIL", "").strip()
        password = os.getenv("SEED_ADMIN_PASSWORD", "").strip()
        name = os.getenv("SEED_ADMIN_NAME", "Admin User").strip()

        if not email or not password:
            raise SystemExit(
                "Missing SEED_ADMIN_EMAIL or SEED_ADMIN_PASSWORD env vars.\n"
                "Example:\n"
                "  SEED_ADMIN_EMAIL=you@ucsb.edu SEED_ADMIN_PASSWORD='strong-password' python -m app.seed_admin"
            )

        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing:
            if existing.role != models.UserRole.admin:
                existing.role = models.UserRole.admin
                db.add(existing)
                db.commit()
            print(f"Admin already exists: {email}")
            return

        admin = models.User(
            name=name,
            email=email,
            role=models.UserRole.admin,
            hashed_password=hash_password(password),
            notify_email=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"Created admin: {admin.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
