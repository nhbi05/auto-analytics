"""WSGI entry point for production servers."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "member_analytics_project.settings")

application = get_wsgi_application()
