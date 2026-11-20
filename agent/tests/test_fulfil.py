from agent import fulfil


def test_detect_store():
    assert fulfil.detect_store("https://www.walmart.com/ip/x/123")[0] == "Walmart"
    assert fulfil.detect_store("https://www.target.com/p/x/-/A-1")[0] == "Target"
    assert fulfil.detect_store("https://evil-target.com/p") is None
    assert fulfil.detect_store("https://amazon.com/dp/1") is None


def test_product_id():
    assert fulfil.product_id("https://www.walmart.com/ip/Folgers/578550306") == "578550306"
    assert fulfil.product_id("https://www.target.com/p/x/-/A-26400934") == "26400934"
    assert fulfil.product_id("https://www.target.com/p/x") == ""


def test_shape_truncates_and_sets_error():
    ok = fulfil.shape(True, "Target", "u", "x" * 500, "s.png")
    assert ok["ok"] and len(ok["cart_text"]) == 300 and ok["error"] is None
    bad = fulfil.shape(False, "Walmart", error="blocked")
    assert not bad["ok"] and bad["error"] == "blocked"
    assert set(bad) == {"ok", "store", "cart_url", "cart_text", "screenshot", "error"}


def test_block_patterns():
    assert fulfil.BLOCK_PATTERNS.search("Robot or human? Activate and hold the button")
    assert not fulfil.BLOCK_PATTERNS.search("Folgers Classic Roast, added to cart")


def test_guards_run_offline(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_BROWSER_WSS", raising=False)
    assert "unsupported" in fulfil.add_to_cart("https://amazon.com/x")["error"]
    t = "https://www.target.com/p/x/-/A-26400934"
    assert "quantity" in fulfil.add_to_cart(t, 2)["error"]
    assert "not set" in fulfil.add_to_cart(t)["error"]
