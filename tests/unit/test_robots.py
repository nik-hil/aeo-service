from aeo_mvp.crawler.robots import parse_robots, robots_pass_value
from aeo_mvp.crawler.discover import same_host, normalize_url


def test_robots_allow_aeobot():
    text = "User-agent: AEOBot\nAllow: /\nUser-agent: *\nDisallow: /\n"
    rules = parse_robots(text, "AEOBot/0.1 (+research; respectful)")
    assert robots_pass_value(rules, "/") == 1.0


def test_robots_disallow():
    text = "User-agent: *\nDisallow: /\n"
    rules = parse_robots(text, "AEOBot")
    assert robots_pass_value(rules, "/") == 0.0


def test_robots_missing_partial():
    assert robots_pass_value(None, "/") == 0.5


def test_same_host():
    assert same_host("https://Example.com/a", "example.com")
    assert not same_host("https://evil.com/", "example.com")


def test_normalize_url():
    assert normalize_url("https://Example.com/Path#frag").endswith("/Path")
