import pygame


_BLUR_DOWNSCALE_FACTOR = 3
_GAUSSIAN_BLUR_RADIUS = 4


def blur_surface(surface: pygame.Surface) -> pygame.Surface:
    """Applies a smooth Gaussian blur, with a scaling fallback for older Pygame."""
    gaussian_blur = getattr(pygame.transform, "gaussian_blur", None)
    if gaussian_blur is not None:
        width, height = surface.get_size()
        reduced_size = (
            max(1, width // _BLUR_DOWNSCALE_FACTOR),
            max(1, height // _BLUR_DOWNSCALE_FACTOR),
        )
        reduced = pygame.transform.smoothscale(surface, reduced_size)
        blurred = gaussian_blur(
            reduced,
            _GAUSSIAN_BLUR_RADIUS,
            repeat_edge_pixels=True,
        )
        return pygame.transform.smoothscale(blurred, (width, height))

    width, height = surface.get_size()
    reduced_size = (max(1, width // 10), max(1, height // 10))
    reduced = pygame.transform.smoothscale(surface, reduced_size)
    return pygame.transform.smoothscale(reduced, (width, height))
