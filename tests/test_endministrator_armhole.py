import pytest

from engine.endministrator_armhole import (choose_sleeve_shoulder_station,
                                           distribute_sleeve_cap_ease,
                                           front_zip_armhole_path,
                                           sleeve_cap_path)


def test_armhole_rejects_missing_declared_underarm():
    outline = [(0, 10), (2, 8), (4, 6), (6, 4), (0, 0), (0, 10)]
    with pytest.raises(ValueError, match="underarm"):
        front_zip_armhole_path(outline, 30)


def test_sleeve_cap_rejects_nonreturning_end():
    with pytest.raises(ValueError, match="cap end"):
        sleeve_cap_path([(0, 1), (1, 0), (2, 2), (0, 1.5)])


def test_sleeve_cap_ease_is_concentrated_near_crown_not_underarm():
    arcs = [0, 2, 4, 6, 8, 10]
    front = distribute_sleeve_cap_ease(arcs, 9, crown_at_start=False)
    back = distribute_sleeve_cap_ease(arcs, 9, crown_at_start=True)
    assert front[0] == back[0] == 0
    assert front[-1] == back[-1] == 9
    assert all(b > a for a, b in zip(front, front[1:]))
    assert all(b > a for a, b in zip(back, back[1:]))
    assert front[1] > back[1]  # front underarm is at the start
    assert back[-1] - back[-2] > front[-1] - front[-2]  # back underarm at end
    assert front[1] == pytest.approx(1.992)
    assert back[-1] - back[-2] == pytest.approx(1.992)


def test_notch_anchored_ease_preserves_both_underarm_intervals():
    arcs = [0, 2, 4, 6, 8, 10]
    front = distribute_sleeve_cap_ease(
        arcs, 9, crown_at_start=False, no_ease_from_underarm_cm=4)
    back = distribute_sleeve_cap_ease(
        arcs, 9, crown_at_start=True, no_ease_from_underarm_cm=4)
    assert front[:3] == pytest.approx([0, 2, 4])
    assert back[-3:] == pytest.approx([5, 7, 9])
    assert front[-1] == back[-1] == 9
    assert all(b > a for a, b in zip(front, front[1:]))
    assert all(b > a for a, b in zip(back, back[1:]))


@pytest.mark.parametrize("notch", [-1, 0, 9, 10, float("nan")])
def test_notch_anchored_ease_rejects_invalid_anchor(notch):
    with pytest.raises(ValueError, match="notch"):
        distribute_sleeve_cap_ease(
            [0, 2, 4, 6, 8, 10], 9, crown_at_start=False,
            no_ease_from_underarm_cm=notch)


@pytest.mark.parametrize("arcs,host", [([0, 1, 1], 2),
                                          ([0, 1, 2], 3),
                                          ([0, 1, 10], 1)])
def test_sleeve_cap_ease_rejects_unsewable_paths(arcs, host):
    with pytest.raises(ValueError):
        distribute_sleeve_cap_ease(arcs, host, crown_at_start=False)


def test_shoulder_station_balances_asymmetric_front_and_back_armholes():
    cap = [(x, abs(x - 5) * .1) for x in range(11)]
    pivot = choose_sleeve_shoulder_station(cap, 3.6, 5.4)
    assert pivot == 4


def test_shoulder_station_rejects_cap_that_is_too_short():
    cap = [(x, abs(x - 5) * .1) for x in range(11)]
    with pytest.raises(ValueError, match="No sewable shoulder station"):
        choose_sleeve_shoulder_station(cap, 6, 6)
