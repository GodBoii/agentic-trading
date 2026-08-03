# python-backend/celery_app.py

from celery import Celery
import config

# ---------------------------------------------------------------------------
# SINGLE SOURCE OF TRUTH FOR CELERY
# ---------------------------------------------------------------------------
# This file creates and configures the Celery application instance.
# Any part of the application that needs access to the Celery app (like workers,
# Flower, or the web app itself) should import the `celery_app` object from here.
# This ensures that all components are using the exact same configuration.
# ---------------------------------------------------------------------------

# Instantiate the Celery app. The first argument is the name of the current module.
celery_app = Celery(__name__)

# Load the configuration directly from our centralized config.py module.
# This is the critical step that provides the Redis broker URL to Celery.
celery_app.conf.update(config.CELERY_CONFIG)

# Optional: If you later create a tasks.py file to define Celery tasks,
# uncomment the line below to auto-discover them.
# celery_app.autodiscover_tasks(['tasks'])