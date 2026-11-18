def initialize_board_coordinates(context, board_image, flipped=False):
    """Builds logical-square to screen-coordinate mappings for either viewpoint."""
    context.square_length = board_image.get_rect().width // 8
    context.chessboard_coordinates.clear()
    for board_x in range(8):
        context.chessboard_coordinates.append([])
        for board_y in range(8):
            screen_x = 7 - board_x if flipped else board_x
            screen_y = board_y if flipped else 7 - board_y
            context.chessboard_coordinates[board_x].append([
                context.board_offset_x + screen_x * context.square_length,
                context.board_offset_y + screen_y * context.square_length,
            ])
