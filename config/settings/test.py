from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

MEDIA_ROOT = BASE_DIR / ".test-media"  # noqa: F405
HOMEX_AUDIO_TEMP_ROOT = BASE_DIR / ".test-audio-temporal"  # noqa: F405
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
