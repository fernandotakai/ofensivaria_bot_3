import os

DEBUG = os.getenv('DEBUG', '1') == '1'
TOKEN = os.getenv('TOKEN', '')
URL = os.getenv('URL', '')

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
