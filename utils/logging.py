from utils.run_config import LOG_DEBUG_ENABLED


def debug_log(message):
    if LOG_DEBUG_ENABLED:
        print(message)
