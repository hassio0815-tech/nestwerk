from .basis import *  # noqa: F403
from .basis import env

DEBUG = True
SECRET_KEY = env("SECRET_KEY") or "entwicklung-nur-lokal"
