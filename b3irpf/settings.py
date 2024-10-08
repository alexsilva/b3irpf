"""
Django settings for b3irpf project.

Generated by 'django-admin startproject' using Django 3.2.16.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""
import sys

import environ
import os.path
from pathlib import Path
import locale

from b3irpf.utils import SecretKey

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

ENV = env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

environ.Env.read_env(os.path.join(BASE_DIR, 'irpf.env'))
try:
    locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
except locale.Error:
    ...
PYTHON_IO_ENCODING = ENV.str('PYTHON_IO_ENCODING', default="utf-8")

sys.stderr.reconfigure(encoding=PYTHON_IO_ENCODING)
sys.stdout.reconfigure(encoding=PYTHON_IO_ENCODING)
sys.stdin.reconfigure(encoding=PYTHON_IO_ENCODING)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = str(SecretKey(BASE_DIR / "irpf.secret"))

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

# verão do projeto
IRPF_VERSION = '1.0.0'

XADMIN_TITLE = "B3 - IRPF"
XADMIN_FOOTER_TITLE = f'irpf - v{IRPF_VERSION}'

XADMIN_DEFAULT_GROUP = 'investor'

# Application definition
CRISPY_ALLOWED_TEMPLATE_PACKS = CRISPY_TEMPLATE_PACK = "bootstrap4"

# assetprice option
SELENIUM_CHROME_EXECUTABLE_PATH = ENV.str("SELENIUM_CHROME_EXECUTABLE_PATH", default=None)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.humanize',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'crispy_bootstrap4',
    'reversion',
    'xadmin',
    'moneyfield',
    'irpf',
    'guardian',
    'assetprice'
]

TICKER_VALIDATOR = "irpf.utils.ticker_validator"

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend', # this is default
    'guardian.backends.ObjectPermissionBackend',
]

# alíquotas de imposto
TAX_RATE = {
    'darf_min_value': '10',
    'stock': {
        'exempt_profit': '20000',  # 20.000,00
        'swing_trade': '15',  # 15%
        'day_trade': '20'  # 20%
    },
    'stock_subscription': {
        'swing_trade': '15',  # 15%
        'day_trade': '20'  # 20%
    },
    'bdr': {
        'swing_trade': '15',  # 15%
        'day_trade': '20'  # 20%
    },
    'fii': {
        'swing_trade': '15',  # 15%
        'day_trade': '20'  # 20%
    },
    'fii_subscription': {
        'swing_trade': '20',  # 20%
        'day_trade': '20'  # 20%
    },
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'irpf.middleware.RequestUtilsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'b3irpf.urls'

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
                'django.template.context_processors.i18n',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'b3irpf.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases
DATABASES = {
    'default': env.db(default=f"sqlite:////{BASE_DIR / 'irpf.sqlite3'}")
}


# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

THOUSAND_SEPARATOR = '.'
USE_THOUSAND_SEPARATOR = True

# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = 'pt-BR'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

MEDIA_ROOT = env.str('MEDIA_ROOT', default=str(BASE_DIR.joinpath("media")))
MEDIA_URL = env.str('MEDIA_URL', default='/media/')

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/
STATIC_ROOT = env.str("STATIC_ROOT", default=str(BASE_DIR.joinpath("static")))
STATIC_URL = env.str("STATIC_URL", default='/static/')

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
