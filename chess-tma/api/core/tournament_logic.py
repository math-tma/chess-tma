"""
Single-elimination bracket generation and prize-pool distribution.

Handles participant counts that aren't a power of 2 by giving byes to
randomly-seeded top slots, so the bracket always resolves cleanly.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class MatchPairing:
    round_number: int
    player1_id: int | None       # None means "bye" for player2
    player2_id: int | None       # None means "bye" for player1


def generate_first_round(participant_ids: list[int], seed: int | None = None) -> list[MatchPairing]:
    """
    Shuffle participants and pair them for round 1 of a single-elimination
    bracket. If the count isn't a power of 2, the shortfall becomes byes
    (a None opponent = automatic advance), given to randomly chosen players
    so no one can predict who gets the easy round.
    """
    if len(participant_ids) < 2:
        raise ValueError("Need at least 2 participants to start a tournament")

    rng = random.Random(seed)
    shuffled = participant_ids[:]
    rng.shuffle(shuffled)

    bracket_size = 2 ** math.ceil(math.log2(len(shuffled)))
    byes_needed = bracket_size - len(shuffled)

    # Pad with None (bye slots) distributed among the shuffled list
    padded = shuffled[:]
    for i in range(byes_needed):
        # insert byes evenly rather than all at the end
        insert_at = (i * 2) + 1
        padded.insert(min(insert_at, len(padded)), None)

    pairings = []
    for i in range(0, len(padded), 2):
        p1 = padded[i]
        p2 = padded[i + 1] if i + 1 < len(padded) else None
        pairings.append(MatchPairing(round_number=1, player1_id=p1, player2_id=p2))

    return pairings


def next_round_pairings(round_number: int, winners_in_order: list[int]) -> list[MatchPairing]:
    """
    Given the winners of the previous round in bracket order, produce the
    next round's pairings. Call this after every match in a round has a
    winner recorded.
    """
    if len(winners_in_order) < 2:
        return []  # tournament is over — winners_in_order[0] is the champion

    pairings = []
    for i in range(0, len(winners_in_order), 2):
        p1 = winners_in_order[i]
        p2 = winners_in_order[i + 1] if i + 1 < len(winners_in_order) else None
        pairings.append(MatchPairing(round_number=round_number, player1_id=p1, player2_id=p2))
    return pairings


def resolve_byes(pairings: list[MatchPairing]) -> tuple[list[MatchPairing], list[int]]:
    """
    Split pairings into ones that need to actually be played vs. ones that
    are byes (auto-advance). Returns (playable_matches, auto_advanced_ids).
    """
    playable = []
    auto_advanced = []
    for p in pairings:
        if p.player1_id is None and p.player2_id is not None:
            auto_advanced.append(p.player2_id)
        elif p.player2_id is None and p.player1_id is not None:
            auto_advanced.append(p.player1_id)
        else:
            playable.append(p)
    return playable, auto_advanced


def calculate_prizes(prize_pool: float, distribution: dict[str, float]) -> dict[str, float]:
    """
    distribution example: {"1": 50, "2": 30, "3": 20}  (percentages, should sum to 100)
    Returns: {"1": 500000.0, "2": 300000.0, "3": 200000.0} for a 1,000,000 pool.
    """
    total_pct = sum(distribution.values())
    if not math.isclose(total_pct, 100.0, abs_tol=0.01):
        raise ValueError(f"Prize distribution must sum to 100%, got {total_pct}%")

    return {
        place: round(prize_pool * pct / 100, 2)
        for place, pct in distribution.items()
    }
