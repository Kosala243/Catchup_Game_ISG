"""Apply dual Pygame clock-display integration safely to existing sources.

Run from the repository root. Makes .pre_clock_backup copies and aborts if an
expected integration point has changed. Do not use as an auto-merge tool.
"""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys

ROOT = Path.cwd()


def replace_one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}: {old!r}")
    return text.replace(old, new, 1)


def edit_gui(text: str) -> str:
    if 'clock_provider' in text:
        raise RuntimeError('app.py appears to have a clock-provider change already')
    text = replace_one(text, 'import pygame\n', 'import math\nimport pygame\n', 'app imports')
    text = replace_one(text,
        '        status_provider: Optional[Callable[[], str]] = None,\n',
        '        status_provider: Optional[Callable[[], str]] = None,\n'
        '        clock_provider: Optional[Callable[[], dict]] = None,\n',
        'app signature')
    text = replace_one(text,
        '        self.status_provider = status_provider or (lambda: "")\n',
        '        self.status_provider = status_provider or (lambda: "")\n'
        '        self.clock_provider = clock_provider or (lambda: {})\n',
        'app initialization')
    method = '''    def _draw_game_clocks(self) -> None:
        """Draw live, independent clocks without changing engine accounting.

        Provider format: {"W": (seconds_left, running), "B": (...)}.
        An idle clock stays frozen; only the currently searching AI runs.
        """
        clocks = self.clock_provider()
        if not clocks:
            return
        for i, colour in enumerate((WHITE, BLACK)):
            if colour not in clocks:
                continue
            seconds, running = clocks[colour]
            seconds = max(0.0, float(seconds))
            # Tenths of seconds let short AI moves visibly change the clock.
            shown_tenths = max(0, int(seconds * 10))
            mins, deci = divmod(shown_tenths, 600)
            secs, tenth = divmod(deci, 10)
            remaining = f"{mins:02d}:{secs:02d}.{tenth}"
            left = 520 + 235 * i
            rect = pygame.Rect(left, 9, 220, 34)
            background = (221, 244, 231) if running else (225, 232, 240)
            if seconds <= 10:
                background = (255, 216, 216)
            pygame.draw.rect(self.screen, background, rect, border_radius=7)
            pygame.draw.rect(self.screen, (67, 110, 84) if running else
                             (145, 156, 168), rect, 2, border_radius=7)
            caption = f"{'White' if colour == WHITE else 'Black'}  {remaining}"
            if running:
                caption += "  >"
            ink = (141, 26, 30) if seconds <= 10 else (21, 45, 65)
            label = self.font.render(caption, True, ink)
            self.screen.blit(label, label.get_rect(center=rect.center))

'''
    text = replace_one(text, '    def _render(self) -> None:\n', method + '    def _render(self) -> None:\n', 'clock display method')
    prefix='        self._label(self.heading, self.title_font, (25, 43, 65), 22, 12)\n'
    text = replace_one(text, prefix, prefix + '        self._draw_game_clocks()\n', 'clock display call')
    return text


def edit_human(text: str) -> str:
    if 'clock_provider=' in text:
        raise RuntimeError('human_vs_ai.py appears to be clock-integrated already')
    # Imported only by graphical run(); existing headless controller tests stay unchanged.
    insert = '''    from ..gui.turn_clock import TurnClock

    controller = HumanGameController(human_colour, think_seconds)
    human_clock = TurnClock(think_seconds)

    def sync_clock():
        human_clock.sync(controller.can_input())

    def confirm(cells):
        controller.confirm_turn(cells)
        sync_clock()

    def undo():
        controller.undo()
        sync_clock()

    def restart():
        controller.reset()
        human_clock.reset(think_seconds)
        sync_clock()

    def frame():
        controller.update()
        sync_clock()

    def clock_values():
        return {
            human_colour: (human_clock.time_left(), human_clock.is_running),
            other(human_colour): (controller.ai.clock.time_left(),
                                  controller.ai.clock.is_running),
        }

    sync_clock()
'''
    text = replace_one(text,
        '    controller = HumanGameController(human_colour, think_seconds)\n',
        insert, 'human main setup')
    text = replace_one(text,
        '        controller.state, controller.confirm_turn, controller.undo,\n',
        '        controller.state, confirm, undo,\n',
        'human GUI callbacks')
    text = replace_one(text,
        '        on_restart=controller.reset, on_frame=controller.update,\n',
        '        on_restart=restart, on_frame=frame,\n',
        'human GUI frame callbacks')
    text = replace_one(text,
        '        input_enabled=controller.can_input, status_provider=controller.status,\n',
        '        input_enabled=controller.can_input, status_provider=controller.status,\n'
        '        clock_provider=clock_values,\n',
        'human clock provider')
    return text


def edit_selfplay(text: str) -> str:
    if 'clock_provider=' in text:
        raise RuntimeError('self_play.py appears to be clock-integrated already')
    # This works with the existing VisualSelfPlayController.run() body.
    setup = re.search(r'^(    controller = \w+\(think_seconds, delay_ms\)\n)', text, re.M)
    if setup is None:
        raise RuntimeError('self_play.py: could not find graphical controller setup; inspect manually')
    helper = '''
    def clock_values():
        return {
            colour: (controller.players[colour].clock.time_left(),
                     controller.players[colour].clock.is_running)
            for colour in (WHITE, BLACK)
        }
'''
    text = text[:setup.end()] + helper + text[setup.end():]
    text = replace_one(text,
        '        input_enabled=lambda: False, status_provider=controller.status,\n',
        '        input_enabled=lambda: False, status_provider=controller.status,\n'
        '        clock_provider=clock_values,\n',
        'self-play clock provider')
    return text


def main() -> None:
    paths = {
        ROOT/'src/gui/app.py': edit_gui,
        ROOT/'src/modes/human_vs_ai.py': edit_human,
        ROOT/'src/modes/self_play.py': edit_selfplay,
    }
    generated = ROOT/'src/gui/turn_clock.py'
    if not generated.exists():
        raise RuntimeError('Place provided src/gui/turn_clock.py into the project first')
    proposed = {}
    for path, edit in paths.items():
        if not path.is_file():
            raise RuntimeError(f'Missing project file: {path}')
        original = path.read_text(encoding='utf-8')
        changed = edit(original)
        compile(changed, str(path), 'exec')
        proposed[path] = changed
    for path in proposed:
        shutil.copy2(path, path.with_name(path.name + '.pre_clock_backup'))
    for path, new_text in proposed.items():
        path.write_text(new_text, encoding='utf-8')
        print('Updated:', path.relative_to(ROOT))
    print('Backups saved with .pre_clock_backup suffix. Run python3 -m pytest -q.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ABORTED (no source files changed):', exc, file=sys.stderr)
        sys.exit(1)
