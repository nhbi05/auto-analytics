"""ASGI entry point for compatible production servers."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "member_analytics_project.settings")

application = get_asgi_application()
