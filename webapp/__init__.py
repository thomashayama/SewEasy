"""SewEasy web-service layer: database persistence and Google-account auth.

This package is fork-specific (not part of upstream GarmentCode). It attaches
to the NiceGUI/FastAPI app created by gui.py.
"""

from webapp.db import init_db
from webapp import auth


def setup(app):
    """Initialize the database and register auth routes + account page"""
    init_db()
    auth.register(app)
    from webapp import account_page  # noqa: F401  -- registers @ui.page('/account')
