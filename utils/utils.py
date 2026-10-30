import pygame

_left_click_position = None


def begin_input_frame(events):
    """Zapamiętuje pozycję pierwszego lewego kliknięcia z bieżącej kolejki zdarzeń."""
    global _left_click_position
    _left_click_position = next(
        (event.pos for event in events
         if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1),
        None,
    )


def get_mouse_event():
    """Zwraca pozycję zapamiętanego kliknięcia lub bieżące położenie kursora."""
    if _left_click_position is not None:
        return _left_click_position
    return pygame.mouse.get_pos()


def left_click_event():
    """Informuje, czy w bieżącej klatce zarejestrowano lewe kliknięcie."""
    return _left_click_position is not None