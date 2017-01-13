import os
import logging

DEBUG = os.getenv('DEBUG', '1') == '1'
TOKEN = os.getenv('TOKEN', '')
URL = os.getenv('URL', '')
LOGGING_LEVEL = getattr(logging, os.getenv('LOGGING_LEVEL', 'INFO'), logging.INFO)

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
