"""
Drawing the board with pygame.
"""

import pygame

from ..board.board import Board, WHITE
from ..board.coordinates import all_cells, to_notation
from .layout import hex_corners, hex_to_pixel

BACKGROUND = (245, 245, 240)
GRID_LINE = (90, 90, 90)
CELL_FILL = (222, 232, 245)
WHITE_STONE = (250, 250, 250)
BLACK_STONE = (30, 30, 30)
TEXT_COLOUR = (60, 60, 60)


def draw_board(surface: pygame.Surface, board: Board, size: float, origin, font: pygame.font.Font,
                highlight_cells=()) -> None:
    surface.fill(BACKGROUND)
    highlight_cells = set(highlight_cells)
    for cell in all_cells():
        center = hex_to_pixel(cell, size, origin)
        corners = hex_corners(center, size * 0.95)
        colour = (255, 235, 160) if cell in highlight_cells else CELL_FILL
        pygame.draw.polygon(surface, colour, corners)
        pygame.draw.polygon(surface, GRID_LINE, corners, width=1)

        stone_colour = board.cells[cell]
        if stone_colour is not None:
            stone_rgb = WHITE_STONE if stone_colour == WHITE else BLACK_STONE
            pygame.draw.circle(surface, stone_rgb, (int(center[0]), int(center[1])), int(size * 0.6))
            pygame.draw.circle(surface, GRID_LINE, (int(center[0]), int(center[1])), int(size * 0.6), width=1)
        else:
            label = font.render(to_notation(cell), True, TEXT_COLOUR)
            surface.blit(label, label.get_rect(center=center))
