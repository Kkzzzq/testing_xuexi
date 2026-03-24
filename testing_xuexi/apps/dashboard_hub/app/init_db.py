from __future__ import annotations

from app.database import Base, engine
from app.models import ShareLink, Subscription  # noqa: F401


def main():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    main()
