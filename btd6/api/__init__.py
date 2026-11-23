"""Local HTTP API over the stats database. Serves the JS frontend and the future game mod."""

from btd6.api.app import create_app

__all__ = ["create_app"]
