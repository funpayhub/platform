from __future__ import annotations


__all__ = [
    'CommonFlags',
    'ParameterFlags',
    'PropertiesFlags',
]


class CommonFlags:
    HIDDEN = 'hidden'


class ParameterFlags(CommonFlags):
    HIDDEN_VALUE = 'hidden_value'
    PROTECTED_VALUE = 'protected_value'
    RESTART_REQUIRED = 'restart_required'


class PropertiesFlags(CommonFlags):
    pass
