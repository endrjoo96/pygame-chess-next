import os

import pygame
from pygame.locals import *

from chess import Chess
from utils.gamecontext import GameContext
from utils import utils


class Game:

    def __init__(self):
        context = GameContext()
        # flag to know if game menu has been showed
        self.menu_showed = False
        # flag to set game loop
        self.running = True
        # base folder for program resources
        self.resources = "res"

        # initialize game window
        pygame.display.init()
        # initialize font for text
        pygame.font.init()

        # create game window
        self.screen = pygame.display.set_mode([context.screen_width, context.screen_height])

        # set background color
        self.screen.fill(context.bg_color)

        # get location of chess board image
        board_src = os.path.join(self.resources, "board.png")
        # load the chess board image
        self.board_img = pygame.image.load(board_src).convert()

        # set window caption
        pygame.display.set_caption(context.window_title)

        # set game icon
        pygame.display.set_icon(pygame.image.load(context.icon_src))
        # update display
        pygame.display.flip()
        # set game clock
        self.clock = pygame.time.Clock()

    def start_game(self):
        context = GameContext()

        """Function containing main game loop"""

        # get the width of a chess board square
        context.square_length = self.board_img.get_rect().width // 8

        # calculate coordinates of the each square on the board
        for x in range(0, 8):
            context.chessboard_coordinates.append([])
            for y in range(0, 8):
                context.chessboard_coordinates[x].append([context.board_offset_x + (x * context.square_length),
                                                          context.board_offset_y + (y * context.square_length)])
            context.chessboard_coordinates[x].reverse()

        # create class object that handles the gameplay logic
        self.chess = Chess(self.screen)

        # game loop
        while self.running:
            self.clock.tick(20)
            # poll events
            for event in pygame.event.get():
                # get keys pressed
                key_pressed = pygame.key.get_pressed()
                # check if the game has been closed by the user
                if event.type == pygame.QUIT or key_pressed[K_ESCAPE]:
                    # set flag to break out of the game loop
                    self.running = False
                elif key_pressed[K_SPACE]:
                    self.chess.reset()

            if not self.menu_showed:
                self.menu()
            else:
                self.game()

            # for testing mechanics of the game
            # self.game()

            # update display
            pygame.display.flip()
            # update events
            pygame.event.pump()

        # call method to stop pygame
        pygame.quit()

    def menu(self):
        context = GameContext()
        """method to show game menu"""
        # black color
        black_color = (0, 0, 0)
        # coordinates for "Play" button
        start_btn = pygame.Rect(270, 300, 100, 50)
        # show play button
        pygame.draw.rect(self.screen, black_color, start_btn)

        # white color
        white_color = (255, 255, 255)
        # create fonts for texts
        big_font = pygame.font.SysFont(context.comic_sans_font, 50)
        small_font = pygame.font.SysFont(context.comic_sans_font, 20)
        # create text to be shown on the game menu
        welcome_text = big_font.render("Chess", False, black_color)
        created_by = small_font.render("Created by Sheriff", True, black_color)
        start_btn_label = small_font.render("Play", True, white_color)

        # show welcome text
        self.screen.blit(welcome_text,
                         ((self.screen.get_width() - welcome_text.get_width()) // 2,
                          150))
        # show credit text
        self.screen.blit(created_by,
                         ((self.screen.get_width() - created_by.get_width()) // 2,
                          self.screen.get_height() - created_by.get_height() - 100))
        # show text on the Play button
        self.screen.blit(start_btn_label,
                         ((start_btn.x + (start_btn.width - start_btn_label.get_width()) // 2,
                           start_btn.y + (start_btn.height - start_btn_label.get_height()) // 2)))

        # get pressed keys
        key_pressed = pygame.key.get_pressed()
        #

        # check if left mouse button was clicked
        if utils.left_click_event():
            # call function to get mouse event
            mouse_coords = utils.get_mouse_event()
            # check if "Play" button was clicked
            if start_btn.collidepoint(mouse_coords[0], mouse_coords[1]):
                # change button behavior as it is hovered
                pygame.draw.rect(self.screen, white_color, start_btn, 3)

                # change menu flag
                self.menu_showed = True
        # check if enter or return key was pressed
        elif key_pressed[K_RETURN]:
            self.menu_showed = True

    def game(self):
        context = GameContext()
        # background color
        color = (0, 0, 0)
        # set backgound color
        self.screen.fill(color)

        # show the chess board
        self.screen.blit(self.board_img, context.board_starting_point)

        # call self.chess. something
        winner = self.chess.play_turn()
        # draw pieces on the chess board
        self.chess.draw_pieces()

        if winner:
            self.declare_winner(winner)

    def declare_winner(self, winner):
        context = GameContext()
        # background color
        bg_color = (255, 255, 255)
        # set background color
        self.screen.fill(bg_color)
        # black color
        black_color = (0, 0, 0)
        # coordinates for play again button
        reset_btn = pygame.Rect(250, 300, 140, 50)
        # show reset button
        pygame.draw.rect(self.screen, black_color, reset_btn)

        # white color
        white_color = (255, 255, 255)
        # create fonts for texts
        big_font = pygame.font.SysFont(context.comic_sans_font, 50)
        small_font = pygame.font.SysFont(context.comic_sans_font, 20)

        # text to show winner
        text = str(winner.get_color().value).capitalize() + " wins!"
        winner_text = big_font.render(text, False, black_color)

        # create text to be shown on the reset button
        reset_label = "Play Again"
        reset_btn_label = small_font.render(reset_label, True, white_color)

        # show winner text
        self.screen.blit(winner_text,
                         ((self.screen.get_width() - winner_text.get_width()) // 2,
                          150))

        # show text on the reset button
        self.screen.blit(reset_btn_label,
                         ((reset_btn.x + (reset_btn.width - reset_btn_label.get_width()) // 2,
                           reset_btn.y + (reset_btn.height - reset_btn_label.get_height()) // 2)))

        # get pressed keys
        key_pressed = pygame.key.get_pressed()

        # check if left mouse button was clicked
        if utils.left_click_event():
            # call function to get mouse event
            mouse_coords = utils.get_mouse_event()

            # check if reset button was clicked
            if reset_btn.collidepoint(mouse_coords[0], mouse_coords[1]):
                # change button behavior as it is hovered
                pygame.draw.rect(self.screen, white_color, reset_btn, 3)

                # change menu flag
                self.menu_showed = True
            # check if enter or return key was pressed
            elif key_pressed[K_RETURN]:
                self.menu_showed = True
            # reset game
            self.chess.reset()
