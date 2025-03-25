import pygame


def get_mouse_event():
    # get coordinates of the mouse
    return pygame.mouse.get_pos()


def left_click_event():
    return pygame.mouse.get_pressed()[0]