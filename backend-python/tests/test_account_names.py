from cryptobridge.utils.account_names import broker_display_name


def test_short_hyphenated_broker_code_keeps_the_suffix():
    assert broker_display_name("Funded-XX", "501234") == "Funded-XX1234"


def test_longer_broker_name_uses_six_letters():
    assert broker_display_name("FundedNext Ltd", "9988771234") == "Funded-1234"


def test_spaces_do_not_count_as_letters():
    assert broker_display_name("Delta Exchange", "42") == "DeltaE-0042"
