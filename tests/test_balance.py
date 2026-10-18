"""A small run of the balance sim, so a tweak to the budgets can't quietly wreck fights."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import balance  # noqa: E402


def test_generated_fights_stay_winnable_but_not_free():
    results = balance.run(worlds=12, seeds=6)
    for name, (rate, n) in results.items():
        assert n > 0, name
        assert 0.7 <= rate <= 0.99, f"{name}: {rate:.0%}"
