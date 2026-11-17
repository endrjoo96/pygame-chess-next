import pygame

from utils.visual import blur_surface


def test_blur_surface_preserves_size_and_softens_hard_edges():
    surface = pygame.Surface((100, 100))
    for x in range(100):
        color = (255, 255, 255) if x % 4 < 2 else (0, 0, 0)
        pygame.draw.line(surface, color, (x, 0), (x, 99))

    blurred = blur_surface(surface)

    assert blurred.get_size() == surface.get_size()
    assert blurred.get_at((50, 50)).r not in (0, 255)
