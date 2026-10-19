"""Deterministic verification of human-side GUI timer without Pygame."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.gui.turn_clock import TurnClock

now = [100.0]
c = TurnClock(600, now=lambda: now[0])
assert c.time_left() == 600
c.sync(True)
now[0] += 2.5
assert abs(c.time_left() - 597.5) < 1e-8
c.sync(False)
now[0] += 30
assert abs(c.time_left() - 597.5) < 1e-8, 'Clock did not stop on opponent turn'
c.sync(True)
now[0] += 7.5
c.sync(False)
assert abs(c.time_left() - 590) < 1e-8
c.reset(600)
assert c.time_left() == 600 and not c.is_running
print('PASS: human turn clock starts, stops, does not refund time, and resets.')
