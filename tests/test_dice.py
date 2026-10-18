import pytest

from dungeon.dice import Dice, ScriptedDice, parse


def test_parse():
    assert parse("2d6+3") == (2, 6, 3)
    assert parse("d20") == (1, 20, 0)
    assert parse("1d4-1") == (1, 4, -1)
    with pytest.raises(ValueError):
        parse("two dice")


def test_same_seed_same_rolls():
    a, b = Dice(7), Dice(7)
    assert [a.d(20) for _ in range(10)] == [b.d(20) for _ in range(10)]


def test_carries_on_from_count():
    a = Dice(7)
    first = [a.d(20) for _ in range(5)]
    resumed = Dice(7, count=3)
    assert resumed.d(20) == first[3]


def test_crit_doubles_dice_not_modifier():
    r = ScriptedDice([3, 4]).roll("1d6+2", crit=True)
    assert r["rolls"] == [3, 4] and r["total"] == 9


def test_total_never_negative():
    assert ScriptedDice([1]).roll("1d4-3")["total"] == 0
