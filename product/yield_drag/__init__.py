"""O1 Yield-Drag Analyst — see README.md and yield_drag_report.py docstring.

Lazy re-export (PEP 562) so `from product.yield_drag import analyze` works
without eagerly importing the module — which would double-import under
`python -m product.yield_drag.yield_drag_report` and warn.
"""
__all__ = ["analyze", "render_report", "YieldDragResult"]


def __getattr__(name):
    if name in __all__:
        from product.yield_drag import yield_drag_report as _m
        return getattr(_m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
