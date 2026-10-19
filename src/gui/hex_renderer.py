"""Render Catchup's 61 labelled pointy-top hexes and stone placements."""

import pygame

from ..board.board import Board, WHITE
from ..board.coordinates import all_cells, to_notation
from .layout import hex_corners, hex_to_pixel

BACKGROUND = (247, 250, 253)
GRID_LINE = (102, 120, 138)
CELL_FILL = (215, 230, 242)
WHITE_STONE = (253, 253, 251)
BLACK_STONE = (35, 44, 59)
TEXT_COLOUR = (43, 65, 82)

def draw_board(surface: pygame.Surface, board: Board, size: float, origin,
               font: pygame.font.Font, highlight_cells=()) -> None:
    surface.fill(BACKGROUND)
    highlighted = set(highlight_cells)
    for cell in all_cells():
        center = hex_to_pixel(cell, size, origin)
        corners = hex_corners(center, size * 0.97)
        fill = (255, 220, 124) if cell in highlighted else CELL_FILL
        pygame.draw.polygon(surface, fill, corners)
        pygame.draw.polygon(surface, GRID_LINE, corners, width=1)
        stone = board.cells[cell]
        if stone is None:
            label = font.render(to_notation(cell), True, TEXT_COLOUR)
            surface.blit(label, label.get_rect(center=center))
        else:
            stone_fill = WHITE_STONE if stone == WHITE else BLACK_STONE
            centre = (round(center[0]), round(center[1]))
            pygame.draw.circle(surface, stone_fill, centre, round(size * 0.59))
            pygame.draw.circle(surface, GRID_LINE, centre, round(size * 0.59), width=2)