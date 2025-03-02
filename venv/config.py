import os

class Config:
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # Set in environment
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))