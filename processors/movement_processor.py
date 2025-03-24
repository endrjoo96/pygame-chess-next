from constants.pos import xy_to_notation

def possible_moves(self, color, name, coord):
    # list to store possible moves of the selected piece
    positions = []
    # find the possible locations to put a piece
    if len(name) > 0:
        # get x, y coordinate
        x_coord, y_coord = coord
        # calculate moves for bishop
        if name == "bishop":
            positions = self.diagonal_moves(positions, name, coord)

        # calculate moves for pawn
        elif name == "pawn":
            # convert list index to dictionary key
            # calculate moves for white pawn
            if color == "black":
                if y_coord + 1 < 8:
                    # get row in front of black pawn
                    front_piece = self.piece_location[xy_to_notation(x_coord, y_coord - 1)][0]

                    # pawns cannot move when blocked by another another pawn
                    if (front_piece[6:] != "pawn"):
                        positions.append([x_coord, y_coord - 1])
                        # black pawns can move two positions ahead for first move
                        if y_coord == 7:
                            positions.append([x_coord, y_coord - 2])

                    # EM PASSANT
                    # diagonal to the left
                    if x_coord - 1 >= 0 and y_coord - 1 < 8:
                        x = x_coord - 1
                        y = y_coord - 1

                        # convert list index to dictionary key
                        to_capture = self.piece_location[xy_to_notation(x, y)][0]

                        if to_capture.startswith("white"):
                            positions.append([x, y])

                    # diagonal to the right
                    if x_coord + 1 < 8 and y_coord - 1 < 8:
                        x = x_coord + 1
                        y = y_coord - 1

                        # convert list index to dictionary key
                        to_capture = self.piece_location[xy_to_notation(x, y)][0]

                        if to_capture.startswith("white"):
                            positions.append([x, y])

            # calculate moves for white pawn
            elif name == "white_pawn":
                if y_coord - 1 >= 0:
                    # get row in front of black pawn
                    front_piece = self.piece_location[xy_to_notation(x_coord, y_coord + 1)][0]

                    # pawns cannot move when blocked by another another pawn
                    if (front_piece[6:] != "pawn"):
                        positions.append([x_coord, y_coord + 1])
                        # black pawns can move two positions ahead for first move
                        if y_coord > 5:
                            positions.append([x_coord, y_coord + 2])

                    # EM PASSANT
                    # diagonal to the left
                    if x_coord - 1 >= 0 and y_coord + 1 >= 0:
                        x = x_coord - 1
                        y = y_coord + 1

                        # convert list index to dictionary key
                        to_capture = self.piece_location[xy_to_notation(x, y)][0]

                        if to_capture.startswith("black"):
                            positions.append([x, y])

                    # diagonal to the right
                    if x_coord + 1 < 8 and y_coord + 1 >= 0:
                        x = x_coord + 1
                        y = y_coord + 1

                        # convert list index to dictionary key
                        to_capture = self.piece_location[xy_to_notation(x, y)][0]

                        if to_capture.startswith("black"):
                            positions.append([x, y])


        # calculate moves for rook
        elif name[6:] == "rook":
            # find linear moves
            positions = self.linear_moves(positions, name, coord)

        # calculate moves for knight
        elif name[6:] == "knight":
            # left positions
            if (x_coord - 2) >= 0:
                if (y_coord - 1) >= 0:
                    positions.append([x_coord - 2, y_coord - 1])
                if (y_coord + 1) < 8:
                    positions.append([x_coord - 2, y_coord + 1])
            # top positions
            if (y_coord - 2) >= 0:
                if (x_coord - 1) >= 0:
                    positions.append([x_coord - 1, y_coord - 2])
                if (x_coord + 1) < 8:
                    positions.append([x_coord + 1, y_coord - 2])
            # right positions
            if (x_coord + 2) < 8:
                if (y_coord - 1) >= 0:
                    positions.append([x_coord + 2, y_coord - 1])
                if (y_coord + 1) < 8:
                    positions.append([x_coord + 2, y_coord + 1])
            # bottom positions
            if (y_coord + 2) < 8:
                if (x_coord - 1) >= 0:
                    positions.append([x_coord - 1, y_coord + 2])
                if (x_coord + 1) < 8:
                    positions.append([x_coord + 1, y_coord + 2])

        # calculate movs for king
        elif name[6:] == "king":
            if (y_coord - 1) >= 0:
                # top spot
                positions.append([x_coord, y_coord - 1])

            if (y_coord + 1) < 8:
                # bottom spot
                positions.append([x_coord, y_coord + 1])

            if (x_coord - 1) >= 0:
                # left spot
                positions.append([x_coord - 1, y_coord])
                # top left spot
                if (y_coord - 1) >= 0:
                    positions.append([x_coord - 1, y_coord - 1])
                # bottom left spot
                if (y_coord + 1) < 8:
                    positions.append([x_coord - 1, y_coord + 1])

            if (x_coord + 1) < 8:
                # right spot
                positions.append([x_coord + 1, y_coord])
                # top right spot
                if (y_coord - 1) >= 0:
                    positions.append([x_coord + 1, y_coord - 1])
                # bottom right spot
                if (y_coord + 1) < 8:
                    positions.append([x_coord + 1, y_coord + 1])

        # calculate movs for queen
        elif name[6:] == "queen":
            # find diagonal positions
            positions = self.diagonal_moves(positions, name, coord)

            # find linear moves
            positions = self.linear_moves(positions, name, coord)

        # list of positions to be removed
        to_remove = []

        # remove positions that overlap other pieces of the current player
        for xy in positions:
            pos = xy_to_notation(xy[0], xy[1])

            # find the pieces to remove
            des_piece_name = self.piece_location[pos][0]
            if (des_piece_name[:5] == name[:5]):
                to_remove.append(xy)

        # remove position from positions list
        for xy in to_remove:
            positions.remove(xy)

    # return list containing possible moves for the selected piece
    return positions