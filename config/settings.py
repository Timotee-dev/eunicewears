"""Eunice Wears settings. Everything environment-specific comes from env vars."""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
RENDER_HOST = env("RENDER_EXTERNAL_HOSTNAME", default="")
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOST}")
SITE_URL = (env("SITE_URL", default="") or (f"https://{RENDER_HOST}" if RENDER_HOST else "http://localhost:8000")).rstrip("/")
SITE_NAME = "Eunice Wears"
DJANGO_ADMIN_PATH = env("DJANGO_ADMIN_PATH", default="backoffice/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.cart",
    "apps.orders",
    "apps.marketing",
    "apps.dashboard",
    "apps.pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
                "apps.core.context_processors.content",
                "apps.cart.context_processors.cart",
            ],
        },
    },
]

# SQLite locally, PostgreSQL in production via DATABASE_URL.
if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db_url("DATABASE_URL")}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- Auth -----------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/account/login/"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24  # verification and reset links live 24h
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sessions live in HttpOnly cookies; JavaScript never sees a credential.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the JS client reads it to send X-CSRFToken

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# --- API ------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "300/min",
        "auth_login": "10/min",
        "auth_register": "10/hour",
        "auth_email": "5/hour",
        "checkout": "30/hour",
        "signup_forms": "10/hour",
        "reviews": "20/hour",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Eunice Wears API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "DESCRIPTION": "Session-authenticated JSON API. All money is integer kobo. Errors always look like "
                   '{"error": {"code", "message", "fields"}}. The Paystack webhook lives at POST /api/payments/webhook/ '
                   "and is authenticated by the x-paystack-signature header.",
    "ENUM_NAME_OVERRIDES": {"OrderStatusEnum": "apps.orders.models.OrderStatus", "PaymentStatusEnum": "apps.orders.models.PaymentStatus",
                            "ReviewStatusEnum": "apps.marketing.models.Review.Status"},
}

# --- Email ----------------------------------------------------------------
EMAIL_HOST = env("EMAIL_HOST", default="")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env("EMAIL_USERNAME", default="")
    EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD", default="")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Eunice Wears <hello@eunicewears.example>")
BREVO_API_KEY = env("BREVO_API_KEY", default="")

# --- Payments -------------------------------------------------------------
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", default="")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
# "paystack" whenever a key is set. With no key, DEBUG falls back to the local sandbox gateway;
# production without a key simply refuses to take payments.
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="paystack" if PAYSTACK_SECRET_KEY or not DEBUG else "sandbox")

# --- Media (product photos). Local disk in development; Cloudinary at deployment.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Static / i18n --------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
CLOUDINARY_URL = env("CLOUDINARY_URL", default="")
STORAGES = {
    "default": {"BACKEND": "apps.core.storage.CloudinaryMediaStorage" if CLOUDINARY_URL
                else "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True
DEFAULT_CURRENCY = "NGN"

# --- Logging: structured, one line per event, no secrets ------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"kv": {"format": "ts=%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "kv"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"eunice": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}

# --- Background jobs ------------------------------------------------------
# With REDIS_URL set, emails and scheduled jobs run on a Celery worker. Without it (local development)
# tasks run inline in the request, so nothing extra has to be started.
CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=not REDIS_URL)
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TASK_IGNORE_RESULT = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "expire-unpaid-orders": {"task": "apps.core.tasks.expire_unpaid_orders", "schedule": 15 * 60},
}
