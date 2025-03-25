from enum import Enum


class EnchantmentType(Enum):
    PASSIVE = 1
    MANDATORY = 2
    STUN_AFTER_CAST = 3
    STUN_AFTER_USE = 4
    REUSABLE = 5
