from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from ..board.coordinates import Cell
from ..game.state import Turn

Action = Tuple[Cell, ...]

class MoveOrdering:
    def __init__(self) -> None:
        self.killers: Dict[int, List[Action]] = defaultdict(list)
        self.history: Dict[Tuple[str, Action], int] = defaultdict(int)

    def order_moves(
        self, moves: Sequence[Turn], colour: str, depth: int,
        pv_move: Optional[Action] = None,
    ) -> List[Turn]:
        """PV first, then killer/history"""
        killers = self.killers.get(depth, ())
        ranked = []
        for index, move in enumerate(moves):
            action = tuple(move)
            pv_priority = 1 if action == pv_move else 0
            # Keep the existing quick-score ranking dominant: killer/history
            # may promote a move by at most two places, avoiding huge regressions.
            killer_priority = 2 - killers.index(action) if action in killers else 0
            history_priority = 1 if self.history[(colour, action)] > 0 else 0
            promotion = min(2, killer_priority + history_priority)
            ranked.append(((-pv_priority, max(0, index - promotion), index), move))
        ranked.sort(key=lambda pair: pair[0])
        return [list(move) for _, move in ranked]

    def record_cutoff(self, colour: str, depth: int, move: Turn) -> None:
        action = tuple(move)
        previous = self.killers[depth]
        if action in previous:
            previous.remove(action)
        previous.insert(0, action)
        del previous[2:]
        self.history[(colour, action)] += depth * depth