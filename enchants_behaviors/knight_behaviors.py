def one_field_in_any_direction(possible_positions_to_move, xy_coord, color, pieces_locations):
    """Dodaje wszystkie sąsiednie pola; filtrowanie pól zajętych wykonuje wywołujący."""
    x, y = xy_coord

    for x_offset in (-1, 0, 1):
        for y_offset in (-1, 0, 1):
            if x_offset == 0 and y_offset == 0:
                continue

            target_x = x + x_offset
            target_y = y + y_offset
            if 0 <= target_x < 8 and 0 <= target_y < 8:
                possible_positions_to_move.append([target_x, target_y])
