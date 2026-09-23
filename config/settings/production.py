from .base import *  # noqa: F403
from .base import required

DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

R2_BUCKET_NAME = required("R2_BUCKET_NAME")
if R2_BUCKET_NAME != "homex-public-media":
    raise RuntimeError("R2_BUCKET_NAME debe ser homex-public-media")

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": required("R2_ACCESS_KEY_ID"),
            "secret_key": required("R2_SECRET_ACCESS_KEY"),
            "bucket_name": R2_BUCKET_NAME,
            "endpoint_url": required("R2_ENDPOINT_URL"),
            "custom_domain": required("HOMEX_MEDIA_PUBLIC_DOMAIN"),
            "querystring_auth": False,
            "file_overwrite": False,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
