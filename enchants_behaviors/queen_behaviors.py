from constants.pos import xy_to_id


def move_up_to_four_fields_through_allies_without_capturing(
        possible_positions_to_move, xy_coord, color, pieces_locations):
    x, y = xy_coord

    for x_offset, y_offset in (
        (0, -1), (0, 1), (-1, 0), (1, 0),
        (-1, -1), (-1, 1), (1, -1), (1, 1),
    ):
        target_x, target_y = x, y
        for _ in range(4):
            target_x += x_offset
            target_y += y_offset
            if not (0 <= target_x < 8 and 0 <= target_y < 8):
                break

            target_piece = pieces_locations[xy_to_id(target_x, target_y)]
            if target_piece.exists():
                if target_piece.get_color() != color:
                    break
                continue

            possible_positions_to_move.append([target_x, target_y])
