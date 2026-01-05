from pathlib import Path
from decouple import config
import os

BASE_DIR = Path(__file__).resolve().parent.parent


REDIS_HOST = config('REDIS_HOST', default='redis')
REDIS_PORT = config('REDIS_PORT', default=6379, cast=int)

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'rest_framework',
    'drf_spectacular',
    
    # Local apps
    'apps.accounts',
    'apps.credits',
    'apps.sms',
    'apps.reports',
    'django_prometheus',

]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',

]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f"redis://{config('REDIS_HOST')}:{config('REDIS_PORT')}/0",
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'accounts.User'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tehran'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.accounts.authentication.APIKeyAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',  # Add this
}

CELERY_WORKER_PREFETCH_MULTIPLIER = 10
CELERY_ACKS_LATE = True
CELERY_BROKER_URL = config('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = f"redis://{config('REDIS_HOST')}:{config('REDIS_PORT')}/1"
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_DEFAULT_QUEUE = 'normal_sms'
CELERY_TASK_QUEUES = {
    'normal_sms': {
        'exchange': 'normal_sms',
        'routing_key': 'normal_sms',
        'queue_arguments': {
            'x-dead-letter-exchange': 'dlx',
            'x-dead-letter-routing-key': 'dead_sms',
        }
    },
    'express_sms': {
        'exchange': 'express_sms',
        'routing_key': 'express_sms',
        'queue_arguments': {
            'x-dead-letter-exchange': 'dlx',
            'x-dead-letter-routing-key': 'dead_sms',
        }
    },
    'dead_sms_queue': {
        'exchange': 'dlx',
        'routing_key': 'dead_sms',
    }
}


SMS_COST_PER_MESSAGE = config('SMS_COST_PER_MESSAGE', default=0.10, cast=float)
EXPRESS_MULTIPLIER = config('EXPRESS_MULTIPLIER', default=2.0, cast=float)
DEFAULT_RATE_LIMIT_PER_MINUTE = config('DEFAULT_RATE_LIMIT_PER_MINUTE', default=100, cast=int)

# Logging Configuration
LOG_DIR = BASE_DIR / 'logs'
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
        print(f"Created logging directory at: {LOG_DIR}")
    except OSError as e:
        print(f"Failed to create logging directory: {e}")
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,

    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s %(exc_info)s',
            'json_ensure_ascii': False,
        },
        'simple': {
            'format': '%(levelname)s %(asctime)s %(module)s %(message)s',
        },
    },

    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
            'level': 'INFO',
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'error.log',
            'maxBytes': 1024 * 1024 * 50,  # 50 MB
            'backupCount': 3,
            'formatter': 'json',
            'level': 'ERROR',
        },
    },

    'loggers': {
        '': {
            'handlers': ['console', 'error_file'],
            'level': 'WARNING',
        },
        'apps': {
            'handlers': ['console', 'error_file'],
            'level': config('LOG_LEVEL', default='WARNING'),
            'propagate': False,
        },
        'django': {
            'handlers': ['console', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'kombu': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'redis': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'SMS Gateway API',
    'DESCRIPTION': 'Professional SMS Gateway Service - Send SMS messages at scale',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/',
    'SECURITY': [
        {
            'ApiKeyAuth': []
        }
    ],
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'ApiKeyAuth': {
                'type': 'apiKey',
                'in': 'header',
                'name': 'X-Api-Key'
            }
        }
    },
    'TAGS': [
        {'name': 'Credits', 'description': 'Credit management endpoints'},
        {'name': 'SMS', 'description': 'SMS operations endpoints'},
        {'name': 'Health', 'description': 'System health check'},
    ],
}