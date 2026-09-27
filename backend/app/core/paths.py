"""Path normalisation shared by the rate limiter and the metrics recorder.

Both need the same answer to the same question: *what is this request, as a
bounded set of labels?* Getting it wrong in either direction is a real problem
rather than a tidiness one.

Too specific and the label space grows without bound. A caller that visits
`/api/v1/suppliers/{random-uuid}` a thousand times a second creates a thousand
series, and a metrics backend will fall over on cardinality long before the
database notices. Path parameters have to collapse.

Too coarse and the signal is gone. `/api/v1/purchase-orders/{id}/invoices` and
`/api/v1/suppliers/{id}` both becoming `/api/v1/{a}/{b}/{c}` tells an operator
nothing about which endpoint is slow.

The rule is therefore the narrowest one that is still correct: a segment is a
parameter if it is numeric or looks like a UUID/opaque hex id, and everything
else is kept verbatim. That is the same rule the rate limiter already used, and
having it in one place means the two cannot drift into disagreeing about which
requests share a bucket and which share a series.
"""
from __future__ import annotations

_HEXISH = frozenset("0123456789abcdefABCDEF-")


def is_parameter_segment(segment: str) -> bool:
    """True if this path segment is an id rather than a route name."""
    if not segment:
        return False
    if segment.isdigit():
        return True
    # A UUID, an opaque hex id, or a ULID. Sixteen characters is the shortest
    # realistic id and is far longer than any route name in this API.
    return len(segment) >= 16 and all(ch in _HEXISH for ch in segment)


def route_label(path: str) -> str:
    """A low-cardinality label for `path`, with parameters collapsed to `{id}`."""
    parts = []
    for segment in path.split("/"):
        if not segment:
            continue
        parts.append("{id}" if is_parameter_segment(segment) else segment)
    return "/" + "/".join(parts) if parts else "/"
