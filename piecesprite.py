import os
import pygame

from gamecontext import GameContext


class PieceSprite(pygame.sprite.Sprite):
    def __init__(self, filename, cols, rows):
        context = GameContext()

        pygame.sprite.Sprite.__init__(self)
        self.pieces = {
            "white_pawn": 5,
            "white_knight": 3,
            "white_bishop": 2,
            "white_rook": 4,
            "white_king": 0,
            "white_queen": 1,
            "black_pawn": 11,
            "black_knight": 9,
            "black_bishop": 8,
            "black_rook": 10,
            "black_king": 6,
            "black_queen": 7
        }
        self.spritesheet = pygame.image.load(filename).convert_alpha()
        self.thumbnail = pygame.image.load(filename)
        self.thumbnail = pygame.transform.scale(self.thumbnail,
                                                (self.thumbnail.get_width() / 2, self.thumbnail.get_height() / 2))

        self.cols = cols
        self.rows = rows
        self.cell_count = cols * rows

        self.rect = self.spritesheet.get_rect()
        w_spritesheet = context.piece_cell_width = self.rect.width // self.cols
        h_spritesheet = context.piece_cell_height = self.rect.height // self.rows

        self.thumb_rect = self.thumbnail.get_rect()
        w_thumbnail = context.piece_cell_thumbnail_width = float(self.thumb_rect.width / self.cols).__round__()
        h_thumbnail = context.piece_cell_thumbnail_height = float(self.thumb_rect.height / self.rows).__round__()

        self.cells = list([(i % cols * w_spritesheet, i // cols * h_spritesheet, w_spritesheet, h_spritesheet) for i in
                           range(self.cell_count)])
        self.cells_thumbnail = list(
            [(i % cols * w_thumbnail, i // cols * h_thumbnail, w_thumbnail, h_thumbnail) for i in
             range(self.cell_count)])

    def draw(self, surface, piece_name, coords, thumbnail=False):
        context = GameContext()
        piece_index = self.pieces[piece_name]
        if thumbnail:
            background = pygame.Surface((context.piece_cell_thumbnail_width, context.piece_cell_thumbnail_height), pygame.SRCALPHA)
            background.fill([255, 255, 255, 40])
            surface.blit(background, coords)
            surface.blit(self.thumbnail, coords, self.cells_thumbnail[piece_index])
        else:
            surface.blit(self.spritesheet, coords, self.cells[piece_index])
