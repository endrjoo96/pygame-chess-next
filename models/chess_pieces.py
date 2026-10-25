from typing import List, Optional, Tuple

from constants.enchantment_type import EnchantmentType
from constants.piece_color import COLOR
from constants.piece_type import PIECE_TYPE
from models.enchantments import Enchantment


class Piece:
    PROMOTION_TYPES = {
        PIECE_TYPE.PAWN: PIECE_TYPE.KNIGHT,
        PIECE_TYPE.KNIGHT: PIECE_TYPE.BISHOP,
        PIECE_TYPE.BISHOP: PIECE_TYPE.ROOK,
        PIECE_TYPE.ROOK: PIECE_TYPE.QUEEN,
    }
    PROMOTION_STUN_TURNS = {
        PIECE_TYPE.PAWN: 1,
        PIECE_TYPE.KNIGHT: 2,
        PIECE_TYPE.BISHOP: 3,
        PIECE_TYPE.ROOK: 4,
    }

    def __init__(
        self, color: COLOR = COLOR.EMPTY, piece_type: PIECE_TYPE = PIECE_TYPE.EMPTY,
        starting_position: Optional[int] = None,
    ):
        self.__color: COLOR = color
        self.__type: PIECE_TYPE = piece_type
        self.__starting_position = starting_position
        self.__enchantments: List[Enchantment] = []
        self.__delayed_enchantments: List[Tuple[Enchantment, int]] = []
        self.__stun_effects: List[Tuple[Enchantment, int]] = []
        self.__stunned_turns_remaining = 0

    def full_name(self) -> str:
        if not self.exists():
            return ""
        return self.__color.value + "_" + self.__type.value

    def get_type(self) -> PIECE_TYPE:
        return self.__type

    def get_starting_position(self) -> Optional[int]:
        return self.__starting_position

    def can_be_promoted(self) -> bool:
        return self.__type in self.PROMOTION_TYPES

    def get_promotion_stun_turns(self) -> int:
        return self.PROMOTION_STUN_TURNS.get(self.__type, 0)

    def get_promotion_stun_turns_to(self, promoted_type: PIECE_TYPE) -> int:
        piece_type = self.__type
        stun_turns = 0
        while piece_type in self.PROMOTION_TYPES:
            piece_type = self.PROMOTION_TYPES[piece_type]
            stun_turns += 1
            if piece_type == promoted_type:
                return stun_turns
        return 0

    def promote_to(self, promoted_type: PIECE_TYPE) -> bool:
        if self.get_promotion_stun_turns_to(promoted_type) == 0:
            return False
        self.__type = promoted_type
        return True

    def promote(self) -> bool:
        promoted_type = self.PROMOTION_TYPES.get(self.__type)
        if promoted_type is None:
            return False
        self.__type = promoted_type
        return True

    def get_color(self) -> COLOR:
        return self.__color

    def exists(self) -> bool:
        return self.__type != PIECE_TYPE.EMPTY or self.__color != COLOR.EMPTY

    def set_enchantment(self, enchantment: Enchantment):
        if enchantment.is_mandatory():
            self.__enchantments.insert(0, enchantment)
        else:
            self.__enchantments.append(enchantment)

    def get_enchantments_to_alter_behavior(self):
        list_of_behaviors = []
        for enchant in self.__enchantments:
            list_of_behaviors.append(enchant.get_behavior_to_inject())
            if enchant.is_mandatory(): break
        return list_of_behaviors

    def has_passive_enchantment(self) -> bool:
        return any(enchantment.is_passive() for enchantment in self.__enchantments)

    def has_delay_enchantment(self) -> bool:
        return any(
            EnchantmentType.DELAY_BEFORE_USE in enchantment.get_enchantment_types()
            for enchantment in self.__enchantments
        ) or any(
            EnchantmentType.DELAY_BEFORE_USE in enchantment.get_enchantment_types()
            for enchantment, _ in self.__delayed_enchantments
        )

    def get_passive_enchantments(self) -> List[Enchantment]:
        return [enchantment for enchantment in self.__enchantments if enchantment.is_passive()]

    def get_effects(
        self, current_turn: int,
    ) -> List[Tuple[Enchantment, Optional[int], Optional[int]]]:
        effects = [(enchantment, None, None) for enchantment in self.__enchantments]
        effects.extend(
            (enchantment, ready_turn - current_turn, None)
            for enchantment, ready_turn in self.__delayed_enchantments
        )
        effects.extend(
            (enchantment, None, turns_remaining)
            for enchantment, turns_remaining in self.__stun_effects
        )
        return effects

    def remove_passive_enchantments(self):
        self.__enchantments = [
            enchantment for enchantment in self.__enchantments
            if not enchantment.is_passive()
        ]

    def add_delayed_enchantment(self, enchantment: Enchantment, ready_turn: int):
        self.__delayed_enchantments.append((enchantment, ready_turn))

    def get_delayed_enchantments_ready_at(self, turn: int) -> List[Enchantment]:
        ready = [
            enchantment for enchantment, ready_turn in self.__delayed_enchantments
            if ready_turn <= turn
        ]
        self.__delayed_enchantments = [
            (enchantment, ready_turn) for enchantment, ready_turn in self.__delayed_enchantments
            if ready_turn > turn
        ]
        return ready

    def set_stunned_for_turns(self, turns: int):
        self.__stunned_turns_remaining = max(self.__stunned_turns_remaining, turns)

    def add_stun_effect(self, enchantment: Enchantment, turns: int):
        self.__stun_effects.append((enchantment, turns))

    def advance_stun_effects(self):
        self.__stunned_turns_remaining = max(0, self.__stunned_turns_remaining - 1)
        self.__stun_effects = [
            (enchantment, turns_remaining - 1)
            for enchantment, turns_remaining in self.__stun_effects
            if turns_remaining > 1
        ]

    def is_stunned(self) -> bool:
        return self.__stunned_turns_remaining > 0

    def can_receive_enchantment(self) -> bool:
        return not self.is_stunned()

    def clear_effects(self):
        self.__enchantments.clear()
        self.__delayed_enchantments.clear()
        self.__stun_effects.clear()
        self.__stunned_turns_remaining = 0
