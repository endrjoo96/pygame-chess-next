import pygame


def blur_surface(surface: pygame.Surface) -> pygame.Surface:
    """Applies a cached-friendly downscale/upscale blur to a surface."""
    width, height = surface.get_size()
    reduced_size = (max(1, width // 10), max(1, height // 10))
    reduced = pygame.transform.smoothscale(surface, reduced_size)
    return pygame.transform.smoothscale(reduced, (width, height))
