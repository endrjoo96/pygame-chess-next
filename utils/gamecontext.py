import os

from utils.singleton import Singleton


class GameContext(metaclass=Singleton):
    board_offset_x = 300
    board_offset_y = 120

    screen_width = 640 + (board_offset_x * 2)
    screen_height = 640 + (board_offset_y * 2)

    resources = "res"
    comic_sans_font = "comicsansms"

    bg_color = (255, 255, 255)

    piece_cell_width = 0
    piece_cell_height = 0
    piece_cell_thumbnail_width = 0
    piece_cell_thumbnail_height = 0

    window_title = "Chess"
    icon_src = os.path.join(resources, "chess_icon.png")
    board_src = os.path.join(resources, "board.png")
    pieces_src = os.path.join(resources, "pieces.png")
    card_on_board_src = os.path.join(resources, "card_on_board.png")
    card_mod_passive_src = os.path.join(resources, "card_mod_passive.png")
    card_mod_reusable_src = os.path.join(resources, "card_mod_reusable.png")
    card_mod_delay_src = os.path.join(resources, "card_mod_delay.png")
    card_mod_stun_src = os.path.join(resources, "card_mod_stun.png")

    board_starting_point = (board_offset_x, board_offset_y)
    captured_white_starting_point = ()
    captured_black_starting_point = ()

    square_length: int

    chessboard_coordinates = []
    cards_coordinates = []
    captured_white_coordinates = []
    captured_black_coordinates = []

    white_cards_starting_point = ()
    black_cards_starting_point = ()

    white_cards_coordinates = []
    black_cards_coordinates = []

    card_width=0
    card_height=0
