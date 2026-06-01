from personal_shopper.state import ShoppingRequest


def test_default_retailer():
    req = ShoppingRequest(raw_message="Thai curry for 4")
    assert req.preferred_retailer == "kroger"


def test_walmart_retailer():
    req = ShoppingRequest(
        raw_message="pasta near 75035 I shop at walmart",
        preferred_retailer="walmart",
    )
    assert req.preferred_retailer == "walmart"


def test_target_retailer():
    req = ShoppingRequest(
        raw_message="green curry, I shop at target",
        preferred_retailer="target",
    )
    assert req.preferred_retailer == "target"


def test_costco_retailer():
    req = ShoppingRequest(
        raw_message="meal prep near 94103, costco",
        preferred_retailer="costco",
    )
    assert req.preferred_retailer == "costco"


def test_unknown_retailer_defaults_to_kroger():
    req = ShoppingRequest(
        raw_message="curry near me",
        preferred_retailer="wholefoodz",  # typo / unsupported
    )
    # graph._get_retailer normalises this to kroger
    # state itself just stores what was given
    assert req.preferred_retailer == "wholefoodz"
