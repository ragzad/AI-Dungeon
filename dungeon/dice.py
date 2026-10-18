import random
import re

DICE_RE = re.compile(r"^\s*(\d*)\s*d\s*(\d+)\s*(?:([+-])\s*(\d+))?\s*$", re.I)


def parse(expr):
    m = DICE_RE.match(str(expr))
    if not m:
        raise ValueError(f"bad dice expression: {expr!r}")
    count = int(m.group(1) or 1)
    sides = int(m.group(2))
    mod = int(m.group(4) or 0)
    if m.group(3) == "-":
        mod = -mod
    return count, sides, mod


class Dice:
    """Seeded dice.

    Each roll gets its own Random seeded from (seed, count), and the count is
    stored in the save, so loading a game carries on with the same sequence.
    """

    def __init__(self, seed=None, count=0):
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.count = count

    def d(self, sides):
        rng = random.Random(f"{self.seed}:{self.count}")
        self.count += 1
        return rng.randint(1, sides)

    def roll(self, expr, crit=False):
        count, sides, mod = parse(expr)
        if crit:
            count *= 2
        rolls = [self.d(sides) for _ in range(count)]
        return {"expr": expr, "rolls": rolls, "mod": mod, "total": max(0, sum(rolls) + mod)}


class ScriptedDice(Dice):
    """Returns preset results in order. Only used by tests."""

    def __init__(self, results):
        super().__init__(seed=0)
        self.results = list(results)

    def d(self, sides):
        self.count += 1
        if not self.results:
            raise AssertionError("ran out of scripted rolls")
        value = self.results.pop(0)
        return max(1, min(sides, value))
