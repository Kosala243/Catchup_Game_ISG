"""Small Pygame menu; no engine logic lives here.

Run `python main.py` for the menu. Existing `main.py gui/selfplay/tournament`
commands continue to work. Tournament still uses stdin/stdout in the terminal.
"""


def run() -> dict | None:
    try:
        import pygame
    except ImportError as error:
        raise SystemExit("Install Pygame or use the existing CLI: python main.py --help") from error

    pygame.init()
    window = pygame.display.set_mode((730, 570))
    pygame.display.set_caption("Catchup | Choose game mode")
    title = pygame.font.SysFont("arial", 34, bold=True)
    font = pygame.font.SysFont("arial", 21)
    small = pygame.font.SysFont("arial", 15)
    clock = pygame.time.Clock()
    choices = [
        ("Human vs AI — play White", "gui", "W"),
        ("Human vs AI — play Black", "gui", "B"),
        ("AI vs AI — watch the game", "selfplay", None),
        ("Tournament — engine White", "tournament", "W"),
        ("Tournament — engine Black", "tournament", "B"),
        ("Experiment Lab", "lab", None),
    ]
    buttons = [pygame.Rect(100, 100 + n * 63, 530, 51) for n in range(len(choices))]
    # Demo selection is a GUI convenience; the official AI game budget is 600 s.
    budget = 600
    selected = None
    active = True
    while active:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                active = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                active = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                options = (12, 60, 600)
                idx = options.index(budget)
                idx = (idx + (-1 if event.key == pygame.K_LEFT else 1)) % len(options)
                budget = options[idx]
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, (_, mode, side) in zip(buttons, choices):
                    if rect.collidepoint(event.pos):
                        selected = {"mode": mode, "colour": side,
                                    "think_seconds": float(budget)}
                        active = False
                        break
        window.fill((15, 28, 43))
        window.blit(title.render("CATCHUP", True, (238, 247, 252)), (265, 22))
        window.blit(small.render("Select mode | Left / right arrows: AI budget", True,
                                 (168, 199, 215)), (209, 72))
        for rect, (label, _, _) in zip(buttons, choices):
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(window, (24, 131, 144) if hovered else (45, 82, 118),
                             rect, border_radius=9)
            window.blit(font.render(label, True, (244, 251, 254)), (rect.x + 18, rect.y + 11))
        foot = (f"AI time per game: {budget} seconds" +
                "   |   Tournament needs the launching terminal")
        window.blit(small.render(foot, True, (174, 206, 223)), (86, 498))
        window.blit(small.render("Esc closes the menu | CLI launch modes remain available", True,
                                 (174, 206, 223)), (135, 532))
        pygame.display.flip()
        clock.tick(30)
    pygame.quit()
    return selected
