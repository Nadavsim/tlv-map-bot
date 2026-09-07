from scripts.sync_places import looks_like_truncated_fetch


def test_no_guard_needed_when_database_was_empty():
    assert looks_like_truncated_fetch(new_count=50, existing_count=0) is False


def test_flags_a_big_drop_as_likely_truncated():
    assert looks_like_truncated_fetch(new_count=10, existing_count=160) is True


def test_does_not_flag_a_small_expected_drop():
    assert looks_like_truncated_fetch(new_count=150, existing_count=160) is False


def test_does_not_flag_growth():
    assert looks_like_truncated_fetch(new_count=200, existing_count=160) is False


def test_respects_a_custom_ratio():
    assert looks_like_truncated_fetch(new_count=140, existing_count=160, ratio=0.95) is True
    assert looks_like_truncated_fetch(new_count=140, existing_count=160, ratio=0.5) is False


def test_boundary_is_exclusive_below_ratio_not_at_it():
    # new_count exactly at the ratio threshold should not be flagged - only
    # strictly below it.
    assert looks_like_truncated_fetch(new_count=112, existing_count=160, ratio=0.7) is False
