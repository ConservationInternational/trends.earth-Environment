"""GEF CORE LOGGER"""

import logging
import os

from gefcore.api import patch_execution
from gefcore.api import save_log


class LocalLogger(object):
    """Logger implementation for local (dev environment)"""

    @staticmethod
    def debug(text):
        """Debug Level"""
        logging.debug(text)

    @staticmethod
    def info(text):
        """Info Level"""
        logging.info(text)

    @staticmethod
    def warn(text):
        """Warn Level"""
        logging.warn(text)

    @staticmethod
    def error(text):
        """Error Level"""
        logging.error(text)

    @staticmethod
    def send_progress(progress):
        """Send Progress"""
        LocalLogger.info("Progress " + str(progress) + "%")


class ServerLogger(object):
    """Logger implementation for server (prod environment)"""

    @staticmethod
    def debug(text):
        """Debug Level"""
        save_log(json={"text": text, "level": "DEBUG"})
        pass

    @staticmethod
    def info(text):
        """Info Level"""
        save_log(json={"text": text, "level": "INFO"})
        pass

    @staticmethod
    def warn(text):
        """Warn Level"""
        save_log(json={"text": text, "level": "WARN"})
        pass

    @staticmethod
    def error(text):
        """Error Level"""
        save_log(json={"text": text, "level": "ERROR"})
        pass

    @staticmethod
    def send_progress(progress):
        """Send Progress"""
        patch_execution(json={"progress": progress})
        pass


LOGGERS = {"dev": LocalLogger, "prod": ServerLogger}


def get_logger_by_env():
    """Get logger according to theenvironment"""
    env = os.getenv("ENV")
    logger = LOGGERS.get(env)
    return logger
