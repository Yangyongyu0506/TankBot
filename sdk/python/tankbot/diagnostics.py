"""Optional algorithm observations. No Core handles, imports, or implicit authorization."""
from contextlib import contextmanager
from contextvars import ContextVar

_current = ContextVar('tankbot_diagnostic_context', default=None)


@contextmanager
def diagnostic_scope(context):
    token=_current.set(context)
    try:yield
    finally:_current.reset(token)


def diagnostic(name: str, value) -> None:
    """Publish an explicitly granted finite scalar/vector/matrix for this update only."""
    context=_current.get()
    if context is None:raise RuntimeError('diagnostic() 只能在模块 update 内调用')
    context.diagnostic(name,value)
