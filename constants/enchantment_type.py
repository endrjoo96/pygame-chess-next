from enum import Enum


class EnchantmentType(Enum):
    PASSIVE = 1
    MANDATORY = 2
    DELAY_BEFORE_USE = 3
    STUN_AFTER_USE = 4
    REUSABLE = 5
