"""Metrics as production telemetry — VNT-033.

The endpoint already existed and already claimed to speak the Prometheus
exposition format. It did not: every line was emitted as
`vantor_http_requests_total {class="5xx"} 0`, and the format does not permit
whitespace between a metric name and its label set. Prometheus rejects the whole
document on that, so the endpoint returned 200 with a body no scraper would
accept — a scrape that looked healthy and recorded nothing at all.

These tests parse the output the way a scraper would, rather than asserting on
substrings, because the whole defect was a formatting detail that a substring
check happily passes.
"""

from __future__ import annotations

import re

import pytest

from app.core import observe
from app.core.paths import route_label


@pytest.fixture(autouse=True)
def clean_metrics():
    """A known starting point. The counters are process-global by design."""
    observe.reset_metrics()
    yield
    observe.reset_metrics()


def _parse_exposition(text: str) -> dict[str, list[tuple[dict, float]]]:
    """A deliberately strict reader: the subset of the format this endpoint uses.

    Rejects a space between the metric name and the label set, which is the exact
    thing the old renderer did.
    """
    series: dict[str, list[tuple[dict, float]]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?\s+(-?[0-9.eE+]+)$", line)
        assert match, f"not a valid exposition line: {line!r}"
        name, label_block, value = match.group(1), match.group(2), float(match.group(3))
        labels: dict[str, str] = {}
        if label_block:
            for pair in re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"',
                                   label_block):
                # A real scraper unescapes. Not doing so here would have hidden
                # whether `prometheus_text` escaped at all.
                labels[pair[0]] = (pair[1].replace('\\"', '"')
                                         .replace("\\\\", "\\")
                                         .replace("\\n", "\n"))
        series.setdefault(name, []).append((labels, value))
    return series


def test_exposition_parses_as_prometheus_expects():
    observe.record_request("GET", "/api/v1/suppliers", 200, 12.0)
    observe.record_request("GET", "/api/v1/suppliers", 500, 40.0)
    observe.incr("vantor_money_posted", "INR", "actual")

    text = observe.prometheus_text()
    parsed = _parse_exposition(text)

    # No space between name and labels: the bug this endpoint had.
    for name, series in parsed.items():
        for labels, _value in series:
            assert isinstance(labels, dict)

    total = [v for labels, v in parsed["vantor_http_requests_total"] if labels["class"] == "all"]
    assert total and total[0] >= 2


def test_routes_are_labelled_so_a_slow_endpoint_is_findable():
    """The gap that made these counters useless: no route dimension.

    One endpoint taking 3s looked identical to every other endpoint taking 3ms,
    so "which route is slow" was answered by reading access logs by hand.
    """
    for _ in range(20):
        observe.record_request("GET", "/api/v1/spend/summary", 200, 3000.0)
    observe.record_request("GET", "/api/v1/suppliers", 200, 3.0)

    parsed = _parse_exposition(observe.prometheus_text())
    by_route = {labels["route"]: value
                for labels, value in parsed["vantor_route_requests_total"]}

    assert by_route["/api/v1/spend/summary"] == 20
    assert by_route["/api/v1/suppliers"] == 1

    # And the latency is per route, so the slow one is identifiable.
    p99 = {(labels["route"], labels["quantile"]): value
           for labels, value in parsed["vantor_route_latency_ms"]}
    assert p99[("/api/v1/spend/summary", "0.99")] == 3000.0
    assert p99[("/api/v1/suppliers", "0.99")] == 3.0


def test_p99_is_published_not_only_a_mean():
    """A mean hides the tail, and the tail is what an SLO is written against."""
    for ms in range(1, 101):  # 1..100 ms, one sample each
        observe.record_request("GET", "/api/v1/x", 200, float(ms))
    snap = observe.metrics_snapshot()
    assert snap["latency"]["p50Ms"] < snap["latency"]["p95Ms"] < snap["latency"]["p99Ms"]
    # Nearest-rank: p99 of 100 ascending samples lands near the top, not the mean.
    assert snap["latency"]["p99Ms"] >= 95
    assert snap["latency"]["p50Ms"] <= 55
    # A mean would have been ~50.5, which is exactly the number that hides the tail.
    assert snap["latency"]["maxMs"] == 100.0


def test_business_counters_are_declared_before_their_first_event():
    """The JSON snapshot lists them on a fresh install.

    So an operator can tell "zero webhook deliveries" from "this build has never
    heard of webhook deliveries". The Prometheus side deliberately does not emit
    zero-valued series for them - a bare unlabelled series would be double-counted
    by `sum(rate(...))` next to the labelled ones.
    """
    snap = observe.metrics_snapshot()
    for name in ("vantor_webhook_deliveries", "vantor_esign_verifications",
                 "vantor_approvals_decided", "vantor_money_posted",
                 "vantor_ai_answers"):
        assert name in snap["business"], f"{name} is not declared"
        assert snap["business"][name] == {}

    parsed = _parse_exposition(observe.prometheus_text())
    assert "vantor_webhook_deliveries" not in parsed

    observe.incr("vantor_webhook_deliveries", "delivered")
    parsed = _parse_exposition(observe.prometheus_text())
    assert parsed["vantor_webhook_deliveries"][0][0]["event"] == "delivered"


def test_business_counters_accumulate_with_labels():
    observe.incr("vantor_webhook_deliveries", "delivered")
    observe.incr("vantor_webhook_deliveries", "delivered")
    observe.incr("vantor_webhook_deliveries", "dead")

    snap = observe.metrics_snapshot()
    assert snap["business"]["vantor_webhook_deliveries"] == {"delivered": 2, "dead": 1}


def test_label_values_are_escaped():
    """An unescaped quote in a label costs every metric, not one.

    A route or event label containing `"` or `\` would otherwise produce a
    document Prometheus refuses to parse, taking the whole scrape with it.
    """
    observe.incr("vantor_webhook_deliveries", 'weird"value\\with')
    text = observe.prometheus_text()
    parsed = _parse_exposition(text)  # raises if the escaping is wrong
    labels = dict(parsed["vantor_webhook_deliveries"][0][0])
    assert labels["event"] == 'weird"value\\with'


def test_the_route_table_is_bounded():
    """A client hitting a random 404 path must not grow the table without bound.

    Each distinct path is a new series, so an unbounded table is an OOM in
    production reachable by an unauthenticated request.
    """
    for i in range(observe.MAX_ROUTE_SERIES + 250):
        observe.record_request("GET", f"/api/v1/nope/{i:016x}", 404, 1.0)
    snap = observe.metrics_snapshot()
    assert len(snap["routes"]) <= observe.MAX_ROUTE_SERIES


def test_an_unknown_counter_name_does_not_raise():
    """A newer worker must not crash an older web process mid-rollout."""
    observe.incr("vantor_something_added_later", "x")
    assert observe.metrics_snapshot()["business"]["vantor_something_added_later"] == {"x": 1}


# --- route normalisation ---------------------------------------------------

def test_route_labels_collapse_ids_but_keep_route_names():
    assert route_label("/api/v1/suppliers/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee") == "/api/v1/suppliers/{id}"
    assert route_label("/api/v1/purchase-orders/12345") == "/api/v1/purchase-orders/{id}"
    assert route_label("/api/v1/suppliers") == "/api/v1/suppliers"
    assert route_label("/") == "/"
    assert route_label("") == "/"
    # Two different ids share one series, so the label space is bounded.
    assert route_label("/api/v1/suppliers/1111111111111111") == route_label(
        "/api/v1/suppliers/2222222222222222")
    # ...and a short word is a name, not an id, so it is kept.
    assert route_label("/api/v1/spend/summary") == "/api/v1/spend/summary"


def test_the_limiter_and_the_metrics_use_the_same_normaliser():
    """They must agree on which requests share a bucket and which share a series.

    If they diverged, a route could dodge the rate limit while still looking like
    one route on a dashboard, or the reverse.
    """
    from app.core.ratelimit import _route_label

    class R:
        def __init__(self, path):
            self.url = type("U", (), {"path": path})()

    for path in ("/api/v1/suppliers/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                 "/api/v1/purchase-orders/99", "/api/v1/spend/summary"):
        assert _route_label(R(path)) == route_label(path)
