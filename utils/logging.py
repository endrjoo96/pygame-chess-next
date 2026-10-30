from utils.run_config import LOG_DEBUG_ENABLED


def debug_log(message):
    """Wypisuje komunikat diagnostyczny wyłącznie przy włączonym logowaniu debug."""
    if LOG_DEBUG_ENABLED:
        print(message)
