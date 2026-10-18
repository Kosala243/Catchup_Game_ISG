"""Clickable Pygame experiment dashboard for the EXISTING Catchup engine.

Run from the project root:
    python3 -m experiments.catchup_dashboard

The four experiments are ablations at a fixed, seeded legal board position.
A search iteration is one completed depth, NOT one stone placement.
This is a separate developer UI, not part of tournament mode.
"""
from __future__ import annotations

import argparse
from queue import Empty, Queue
from threading import Event, Thread

from experiments.catchup_diagnostics import EXPERIMENTS, run_experiment
from experiments.phase6_common import build_position
from src.board.board import WHITE, BLACK
from src.board.coordinates import all_cells, from_notation
from src.gui.layout import hex_corners, hex_to_pixel
from src.engine.transposition_table import CELL_BITS

W, H = 1280, 865  # Virtual canvas: all existing layout coordinates stay unchanged.


def initial_window_size(desktop_size: tuple[int, int]) -> tuple[int, int]:
    """Fit under the macOS/Windows menu bars and Dock/taskbar.

    Desktop dimensions reported by pygame are logical window coordinates.
    Allow vertical clearance for window decorations and a visible Dock.
    """
    dw, dh = desktop_size
    if dw <= 0 or dh <= 0:
        raise ValueError("desktop dimensions must be positive")
    return min(W, max(1, dw - 80)), min(H, max(1, dh - 160))


def fit_viewport(window_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Return the letterboxed virtual-canvas rect within a real window."""
    dw, dh = window_size
    if dw <= 0 or dh <= 0:
        raise ValueError("window dimensions must be positive")
    ratio = min(dw / W, dh / H)
    scaled_w = max(1, min(dw, round(W * ratio)))
    scaled_h = max(1, min(dh, round(H * ratio)))
    return (dw - scaled_w) // 2, (dh - scaled_h) // 2, scaled_w, scaled_h


def mouse_to_canvas(point: tuple[int, int],
                    window_size: tuple[int, int]) -> tuple[int, int] | None:
    """Translate actual mouse clicks back to the 1280x865 layout."""
    left, top, width, height = fit_viewport(window_size)
    x, y = point
    if not (left <= x < left + width and top <= y < top + height):
        return None  # Ignore clicks in letterbox margins.
    return int((x - left) * W / width), int((y - top) * H / height)


BG = (16, 24, 37)
PANEL = (27, 40, 56)
BORDER = (57, 73, 91)
TEXT = (234, 243, 249)
SUBTEXT = (172, 192, 207)
PRIMARY = (53, 113, 157)
ACTIVE = (23, 140, 132)
AMBER = (237, 187, 83)


def run(*, seed: int = 33, empty_cells: int = 19, max_depth: int = 4,
        budget_seconds: float = 4.0) -> None:
    try:
        import pygame
    except ImportError as error:
        raise SystemExit("Pygame required: python3 -m pip install -r requirements.txt") from error

    pygame.init()
    desktop = pygame.display.get_desktop_sizes()[0]
    actual_size = initial_window_size(desktop)
    display = pygame.display.set_mode(actual_size, pygame.RESIZABLE)
    # Draw everything at its original 1280x865 coordinates, then scale once.
    # This keeps fonts, board geometry, button locations, and spacing in sync.
    window = pygame.Surface((W, H)).convert()
    pygame.display.set_caption("Catchup | Search experiment dashboard")
    clock = pygame.time.Clock()
    normal = pygame.font.SysFont("consolas", 16)
    small = pygame.font.SysFont("consolas", 14)
    large = pygame.font.SysFont("arial", 25, bold=True)
    header = pygame.font.SysFont("arial", 17, bold=True)

    seed = seed
    empty_cells = empty_cells
    max_depth = max_depth
    budget_seconds = budget_seconds
    events: Queue = Queue()
    worker: Thread | None = None
    cancel = Event()
    rows: list[dict] = []
    report: dict | None = None
    selected = None
    status = "Select Experiment 1-4. All four use the SAME seeded position."
    tt_page = 0
    selected_tt_row = None
    stop = False
    display_position = build_position(seed, empty_cells)

    def font_line(text, pos, *, color=TEXT, font=normal, max_width=None):
        text = str(text)
        if max_width is not None:
            while len(text) > 3 and font.size(text)[0] > max_width:
                text = text[:-4] + "..."
        window.blit(font.render(text, True, color), pos)

    def border(rect, fill=PANEL):
        pygame.draw.rect(window, fill, rect, border_radius=9)
        pygame.draw.rect(window, BORDER, rect, width=1, border_radius=9)

    def button(rect, text, enabled=True, active=False):
        fill = ACTIVE if active else (PRIMARY if enabled else (50, 60, 72))
        pygame.draw.rect(window, fill, rect, border_radius=9)
        font_line(text, (rect.x + 11, rect.y + (rect.height - normal.get_height()) // 2),
                  color=TEXT if enabled else SUBTEXT, max_width=rect.width - 17)

    def controls():
        return [pygame.Rect(20 + i * 317, 84, 300, 52) for i in range(4)]

    def settings_buttons():
        specs = [("seed", 40), ("empty", 325), ("depth", 610), ("budget", 895)]
        btns = {}
        for name, x in specs:
            btns[(name, -1)] = pygame.Rect(x + 165, 175, 36, 32)
            btns[(name, 1)] = pygame.Rect(x + 208, 175, 36, 32)
        return btns

    def current_tt():
        return [] if report is None else report.get("tt_preview", [])

    def launch(number):
        nonlocal worker, rows, report, selected, status, display_position, tt_page, selected_tt_row
        if worker is not None and worker.is_alive():
            return
        display_position = build_position(seed, empty_cells)
        rows = []
        report = None
        selected = number
        tt_page = 0
        selected_tt_row = None
        status = f"Experiment {number}: thinking through successive depths..."
        cancel.clear()
        args = dict(seed=seed, empty_cells=empty_cells, max_depth=max_depth,
                    budget_seconds=budget_seconds)

        def work():
            try:
                run_experiment(number, on_event=events.put, cancel=cancel, **args)
            except Exception as exc:
                events.put({"kind": "error", "message": str(exc)})
        worker = Thread(target=work, daemon=True, name="Catchup-Diagnostics")
        worker.start()

    while not stop:
        try:
            while True:
                update = events.get_nowait()
                kind = update.get("kind")
                if kind == "iteration":
                    rows.append(update["row"])
                    status = f"Completed depth {update['row']['depth']} | best: {update['row']['best_turn']}"
                elif kind == "complete":
                    report = update["report"]
                    result = report["result"]
                    status = (f"Finished: depth {result['completed_depth']} | best {result['best_turn']} "
                              f"| {result['elapsed_seconds']:.2f}s | JSON and CSV saved")
                elif kind == "interrupted":
                    status = f"Budget reached during depth {update['depth']}; keeping deepest completed result."
                elif kind == "error":
                    status = f"Error: {update['message']}"
                elif kind == "started":
                    status = f"Running {update['configuration']} on seeded position {seed}"
        except Empty:
            pass

        busy = worker is not None and worker.is_alive()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                cancel.set()
                stop = True
            elif event.type == pygame.VIDEORESIZE:
                # pygame 2 supports resizing; render scale and hit-testing are
                # recomputed from the new window size on the next frame.
                display = pygame.display.set_mode(
                    (max(1, event.w), max(1, event.h)), pygame.RESIZABLE
                )
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    cancel.set()
                if event.key in (pygame.K_PAGEDOWN, pygame.K_DOWN):
                    tt_page += 1
                if event.key in (pygame.K_PAGEUP, pygame.K_UP):
                    tt_page = max(0, tt_page - 1)
                if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4) and not busy:
                    launch(event.key - pygame.K_1 + 1)
            elif event.type == pygame.MOUSEWHEEL:
                tt_page = max(0, tt_page - event.y)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pt = mouse_to_canvas(event.pos, display.get_size())
                if pt is None:
                    continue
                if not busy:
                    for i, rect in enumerate(controls()):
                        if rect.collidepoint(pt):
                            launch(i + 1)
                            break
                    else:
                        for (setting, direction), rect in settings_buttons().items():
                            if rect.collidepoint(pt):
                                if setting == "seed":
                                    seed = max(0, seed + direction)
                                elif setting == "empty":
                                    empty_cells = min(60, max(1, empty_cells + direction))
                                elif setting == "depth":
                                    max_depth = min(8, max(1, max_depth + direction))
                                elif setting == "budget":
                                    budget_seconds = min(60.0, max(1.0, budget_seconds + direction))
                                display_position = build_position(seed, empty_cells)
                                report, rows, selected = None, [], None
                                selected_tt_row, tt_page = None, 0
                                status = "Position or search setting changed; choose an experiment."
                                break
                if pygame.Rect(1090, 245, 163, 32).collidepoint(pt) and busy:
                    cancel.set()
                    status = "Cancel requested. Current iteration finishes or times out."
                # Data rows render at 583 + 24*i. Map clicks to those rows,
                # not to the 27-pixel approximation used by the old UI.
                if 30 <= pt[0] < 925 and 580 <= pt[1] < 796:
                    index = tt_page * 9 + (pt[1] - 580) // 24
                    if 0 <= index < len(current_tt()):
                        selected_tt_row = index

        window.fill(BG)
        font_line("CATCHUP  /  EXPERIMENT LAB", (23, 22), font=large)
        font_line("1 ply = 1 complete turn (1-3 placements) | Iteration = one search depth",
                  (25, 57), color=SUBTEXT, font=small)
        for exp, rect in zip(EXPERIMENTS, controls()):
            button(rect, f"{exp.number}.  {exp.title}", not busy, exp.number == selected)

        border(pygame.Rect(20, 151, 1240, 75))
        for label, value, x in (("Seed", seed, 40), ("Empty cells", empty_cells, 325),
                                ("Max depth", max_depth, 610), ("Total budget", f"{budget_seconds:g}s", 895)):
            font_line(f"{label}: {value}", (x, 175), max_width=157)
        for rect in settings_buttons().values():
            button(rect, "-" if (rect.x - 40) % 285 == 165 else "+", not busy)
        # Paint +/- explicitly because positions do not share a uniform origin.
        for (_, direction), rect in settings_buttons().items():
            pygame.draw.rect(window, (48, 73, 97) if not busy else (50, 60, 72), rect, border_radius=6)
            font_line("+" if direction == 1 else "-", (rect.x + 12, rect.y + 6))

        border(pygame.Rect(20, 237, 1240, 44))
        font_line(status, (32, 250), color=AMBER if "Error" in status else TEXT, max_width=1020)
        if busy:
            button(pygame.Rect(1090, 245, 163, 32), "Cancel run", True)

        border(pygame.Rect(20, 295, 1240, 210))
        font_line("SEARCH ITERATIONS   (per-depth counts; same position across experiments)",
                  (36, 307), font=header)
        cols = [(38, "Depth"), (112, "Best turn"), (265, "Eval"), (355, "Time"),
                (453, "Nodes"), (552, "Leaves"), (644, "Cutoffs"), (750, "TT hits"),
                (856, "TT stores"), (976, "Table size")]
        for x, label in cols:
            font_line(label, (x, 341), color=SUBTEXT, font=small)
        for idx, row in enumerate(rows[-5:]):
            y = 367 + idx * 25
            values = (row["depth"], row["best_turn"], f"{row['evaluation']:+.2f}",
                      f"{row['elapsed_seconds']:.3f}s", row["nodes"], row["leaves"],
                      row["cutoffs"], row["tt_hits"], row["tt_stores"], row["tt_size"])
            for (x, _), value in zip(cols, values):
                font_line(str(value), (x, y), font=small, max_width=144 if x==112 else 92)

        border(pygame.Rect(20, 515, 1240, 295))
        tt = current_tt()
        info = (report or {}).get("tt_summary", {})
        font_line(f"TRANSPOSITION TABLE   {info.get('size',0):,} entries / "
                  f"{info.get('capacity',0):,} capacity  |  "
                  f"EXACT {info.get('exact',0)}  LOWER {info.get('lower',0)}  UPPER {info.get('upper',0)}",
                  (35, 528), font=header)
        headers = [(33, "Depth"), (112, "Bound"), (212, "Value"),
                   (320, "Best turn"), (495, "To move"), (592, "W score"),
                   (692, "B score"), (792, "W/B stones")]
        for x, h in headers:
            font_line(h, (x, 557), font=small, color=SUBTEXT)
        tt_page = max(0, min(tt_page, max(0, (len(tt) - 1) // 9)))
        for i, entry in enumerate(tt[tt_page * 9:tt_page * 9 + 9]):
            index = tt_page * 9 + i
            y = 583 + i * 24
            if index == selected_tt_row:
                pygame.draw.rect(window, (39, 82, 90), (30, y - 2, 895, 23), border_radius=3)
            cells = (entry["depth"], entry["bound"], f"{entry['value']:+.2f}",
                     entry["best_turn"], entry["to_move"], entry["white_score"],
                     entry["black_score"], f"{entry['white_stones']}/{entry['black_stones']}")
            for (x, _), value in zip(headers, cells):
                font_line(value, (x, y), font=small, max_width=163 if x == 320 else 95)
        if not tt:
            font_line("No TT entries available (experiments 1/2 disable TT).",
                      (36, 596), color=SUBTEXT)
        font_line(f"TT sample: {len(tt)} rows (not the entire table). Page {tt_page + 1}. Scroll/PgDn/PgUp.",
                  (35, 786), font=small, color=SUBTEXT)

        # Mini-board displays the ROOT position, or the selected TT key's
        # exact bitboard occupancy. It never mutates the actual GameState.
        pygame.draw.line(window, BORDER, (955, 554), (955, 796), 1)
        active_entry = (tt[selected_tt_row] if selected_tt_row is not None
                        and selected_tt_row < len(tt) else None)
        font_line("SELECTED TT POSITION" if active_entry else "SEEDED POSITION",
                  (976, 562), font=header)
        origin = (1111, 674)
        highlighted = set()
        displayed_turn = active_entry["best_turn"] if active_entry else (
            report["result"]["best_turn"] if report else "")
        for name in displayed_turn.split():
            if name != "—":
                highlighted.add(from_notation(name))
        wmask = int(active_entry["white_mask"], 16) if active_entry else None
        bmask = int(active_entry["black_mask"], 16) if active_entry else None
        for cell in all_cells():
            x, y = hex_to_pixel(cell, 13.4, origin)
            corners = hex_corners((x, y), 12.5)
            if active_entry:
                value = (WHITE if wmask & CELL_BITS[cell] else
                         BLACK if bmask & CELL_BITS[cell] else None)
            else:
                value = display_position.board.cells[cell]
            col = (237, 192, 91) if cell in highlighted else (92, 111, 128)
            pygame.draw.polygon(window, col, corners, 1)
            if value:
                pygame.draw.circle(window, (246, 247, 244) if value == WHITE else (18, 23, 31),
                                   (round(x), round(y)), 7)
                pygame.draw.circle(window, (165, 178, 185), (round(x), round(y)), 7, 1)
        if active_entry:
            font_line(f"W/B scores {active_entry['white_score']}/{active_entry['black_score']}  "
                      f"side={active_entry['to_move']}", (975, 761), font=small, color=SUBTEXT)
            font_line(f"Bonus flag={int(active_entry['bonus_previous_turn'])}  "
                      f"bound={active_entry['bound']}", (975, 780), font=small, color=SUBTEXT)
        elif report:
            font_line("Gold edges: best root turn", (973, 770), font=small, color=AMBER)

        border(pygame.Rect(20, 824, 1240, 30))
        if report:
            font_line(f"Saved JSON: {report['saved_json']}", (29, 830), font=small, color=SUBTEXT, max_width=1200)
        else:
            font_line("Note: Used same seed/empty/depth/time settings for all four comparisons.",
                      (29, 830), font=small, color=SUBTEXT)
        # Preserve the design's aspect ratio, even after manual resize.
        # All content—including the footer below y=824—fits in the window.
        display.fill(BG)
        left, top, scaled_w, scaled_h = fit_viewport(display.get_size())
        fitted = pygame.transform.smoothscale(window, (scaled_w, scaled_h))
        display.blit(fitted, (left, top))
        pygame.display.flip()
        clock.tick(30)
    pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=33)
    parser.add_argument("--empty-cells", type=int, default=19)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--budget-seconds", type=float, default=4.0)
    args = parser.parse_args()
    if not 1 <= args.empty_cells <= 60 or not 1 <= args.max_depth <= 8 or not 0 < args.budget_seconds <= 600:
        parser.error("Require 1<=empty-cells<=60, 1<=max-depth<=8, 0<budget-seconds<=600")
    run(seed=args.seed, empty_cells=args.empty_cells,
        max_depth=args.max_depth, budget_seconds=args.budget_seconds)


if __name__ == "__main__":
    main()
