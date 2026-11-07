from app.main import WARNING_LIMIT, WINDOW_SWITCH_LIMIT, should_pause_attempt


def test_warning_limit_is_five():
    assert WARNING_LIMIT == 5


def test_third_window_switch_pauses_attempt_but_two_do_not():
    assert WINDOW_SWITCH_LIMIT == 2
    assert not should_pause_attempt(0, 2)
    assert should_pause_attempt(0, 3)
