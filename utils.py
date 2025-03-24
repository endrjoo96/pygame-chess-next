import pygame
from pygame.locals import *
import queue

class Utils:
    def get_mouse_event(self):
        # get coordinates of the mouse
        return pygame.mouse.get_pos()

    def left_click_event(self):
        return pygame.mouse.get_pressed()[0]