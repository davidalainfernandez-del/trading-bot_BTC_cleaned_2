"""
Centralized configuration for the trading bot backend.
"""
import os, time

APP_NAME = os.getenv("APP_NAME", "trading-bot-backend")
APP_VERSION = os.getenv("APP_VERSION", "0.0.0")
GIT_SHA = os.getenv("GIT_SHA", "")

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

START_TIME = time.time()
