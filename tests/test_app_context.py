from __future__ import annotations

import re
from typing import Any
from unittest.mock import Mock
from collections.abc import Callable

import pytest

from hubplatform.app_context import AppContext


def test_stores_values_as_mapping_and_attributes() -> None:
    context = AppContext()

    context['answer'] = 42
    context.update({'name': 'Hub'}, enabled=True)

    assert context['answer'] == 42
    assert context.answer == 42
    assert dict(context) == {'answer': 42, 'name': 'Hub', 'enabled': True}
    assert len(context) == 3
    assert list(context) == ['answer', 'name', 'enabled']


def test_supports_mapping_mutation_methods() -> None:
    context = AppContext()
    context.update({'first': 1, 'second': 2})

    del context['first']
    assert 'first' not in context

    context['third'] = 3
    assert context['third'] == 3

    context.pop('second')
    assert 'second' not in context

    context['last'] = 4
    context.popitem()
    assert 'last' not in context

    context.clear()

    assert dict(context) == {}


@pytest.mark.parametrize(
    'mutation',
    [
        lambda context: context.__setitem__('other', 'value'),
        lambda context: context.__delitem__('key'),
        lambda context: context.update({'other': 'value'}),
        lambda context: context.pop('key'),
        lambda context: context.popitem(),
        lambda context: context.clear(),
    ],
)
def test_lock_blocks_mutations(mutation: Callable[[AppContext], object]) -> None:
    context = AppContext()
    context['key'] = 'value'
    context.lock()

    with pytest.raises(RuntimeError, match=r'^App context is locked\.$'):
        mutation(context)

    assert dict(context) == {'key': 'value'}


def test_check_ready_accepts_complete_and_valid_context() -> None:
    context = AppContext()
    check_token = Mock()
    context['token'] = 'valid-token'
    context['optional-check'] = 'value'
    context.check_items = {
        'token': check_token,
        'optional-check': None,
    }

    context.check_ready()

    check_token.assert_called_once_with('valid-token')


def test_check_ready_reports_missing_item() -> None:
    context = AppContext()
    context.check_items = {'token': None}

    with pytest.raises(
        RuntimeError,
        match=r"^Workflow data not ready: missing key 'token'$",
    ):
        context.check_ready()


@pytest.mark.parametrize(
    ('error', 'message'),
    [
        (
            ValueError('invalid value'),
            "Workflow data not ready: 'token' didnt pass the check.",
        ),
        (
            TypeError('unexpected error'),
            "Workflow data not ready: an error occurred while checking 'token'.",
        ),
    ],
)
def test_check_ready_wraps_checker_errors(error: Exception, message: str) -> None:
    context = AppContext()
    context['token'] = 'value'

    def check_token(value: Any) -> None:
        raise error

    context.check_items = {'token': check_token}

    with pytest.raises(RuntimeError, match=f'^{re.escape(message)}$') as error_info:
        context.check_ready()

    assert error_info.value.__cause__ is error
