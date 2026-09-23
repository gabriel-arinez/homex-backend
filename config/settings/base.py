"""Ajustes compartidos del backend HOMEX."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variable de entorno requerida: {name}")
    return value


def database_from_url(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL debe usar PostgreSQL")
    if not parsed.path or not parsed.path.lstrip("/"):
        raise RuntimeError("DATABASE_URL debe incluir el nombre de la base de datos")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username,
        "PASSWORD": parsed.password,
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
    }


SECRET_KEY = required("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [host for host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if host]
LANGUAGE_CODE = "es-bo"
TIME_ZONE = "America/La_Paz"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "apps.accounts",
    "apps.catalogo",
    "apps.clientes",
    "apps.proformas",
    "apps.pedidos",
    "apps.movimientos_stock",
    "apps.ordenes_trabajo",
    "apps.recibos",
    "apps.notas_entrega",
    "apps.documentos",
    "apps.capturas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
STATIC_URL = "static/"
DATABASES = {"default": database_from_url(required("DATABASE_URL"))}
CORS_ALLOWED_ORIGINS = [
    origin for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "HOMEX Backend API",
    "DESCRIPTION": "API comercial de HOMEX.",
    "VERSION": "v1",
    "SERVE_INCLUDE_SCHEMA": False,
}

MEDIA_URL = os.getenv("HOMEX_MEDIA_URL", "/media/")
MEDIA_ROOT = Path(os.getenv("HOMEX_MEDIA_ROOT", BASE_DIR / ".media"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# F08.2 — Redis transporta IDs; PostgreSQL/outbox conserva el trabajo pendiente.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TRACK_STARTED = False
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_IGNORE_RESULT = True
CELERY_BEAT_SCHEDULE = {
    "publicar-outbox-capturas": {
        "task": "capturas.publicar_outbox",
        "schedule": 5.0,
    },
    "limpiar-audio-temporal": {
        "task": "capturas.limpiar_audio_temporal",
        "schedule": 900.0,
    },
    "reconciliar-outbox-capturas": {
        "task": "capturas.reconciliar_outbox",
        "schedule": 60.0,
    },
}
HOMEX_AUDIO_TEMP_ROOT = Path(os.getenv("HOMEX_AUDIO_TEMP_ROOT", BASE_DIR / ".audio-temporal"))
HOMEX_AUDIO_MAX_BYTES = int(os.getenv("HOMEX_AUDIO_MAX_BYTES", "25000000"))
HOMEX_AUDIO_TTL_SECONDS = int(os.getenv("HOMEX_AUDIO_TTL_SECONDS", "3600"))
HOMEX_OUTBOX_RECONCILE_SECONDS = int(os.getenv("HOMEX_OUTBOX_RECONCILE_SECONDS", "3600"))
HOMEX_ASR_MODEL_PATH = os.getenv("HOMEX_ASR_MODEL_PATH")
HOMEX_ASR_DEVICE = os.getenv("HOMEX_ASR_DEVICE", "cpu")
HOMEX_ASR_COMPUTE_TYPE = os.getenv("HOMEX_ASR_COMPUTE_TYPE", "int8")
