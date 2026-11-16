from .settings import *

# Tests never connect to the application's MySQL database.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
SECURE_SSL_REDIRECT = False
ALLOWED_HOSTS = ["testserver", "localhost"]
