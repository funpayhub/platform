from __future__ import annotations

from typing import Any
from dataclasses import dataclass
from collections.abc import Mapping

import pytest
from hubplatform.expressions.docs import ExpressionDocs
from hubplatform.expressions.syntax import Call, call_decoder
from hubplatform.expressions.traits import TraitsContainer
from hubplatform.expressions.manager import EvaluationResult, ExpressionsManager
from hubplatform.expressions.fragments import Fragment
from hubplatform.expressions.definition import ExpressionCallResult, expression
from hubplatform.expressions.exceptions import ExpressionExecutionError


DOCS = ExpressionDocs(name='test', overview='test')


@dataclass(frozen=True)
class Image(Fragment):
    path: str

    def text_fallback(self) -> str:
        return f'[image {self.path}]'


@dataclass(frozen=True)
class Break(Fragment):
    pass


class Counter:
    def __init__(self) -> None:
        self.calls = 0


@pytest.fixture
def counter() -> Counter:
    return Counter()


@pytest.fixture
def manager(counter: Counter) -> ExpressionsManager:
    manager = ExpressionsManager({})

    @manager.register(call_key='upper')
    @expression(docs=DOCS)
    async def upper(ctx: TraitsContainer, text: str) -> str:
        return text.upper()

    @manager.register(call_key='image')
    @expression(docs=DOCS)
    async def image(ctx: TraitsContainer, path: str) -> Image:
        return Image(path)

    @manager.register(call_key='break')
    @expression(docs=DOCS)
    async def break_(ctx: TraitsContainer) -> Break:
        return Break()

    @manager.register(call_key='path_of')
    @expression(docs=DOCS)
    async def path_of(ctx: TraitsContainer, image: Any) -> str:
        assert isinstance(image, Image)
        return image.path

    @manager.register(call_key='fail')
    @expression(docs=DOCS)
    async def fail(ctx: TraitsContainer) -> str:
        raise RuntimeError('fail')

    @manager.register(call_key='counted')
    @expression(docs=DOCS)
    class Counted:
        """Has a side effect and a renderer, so it must be called only once per call."""

        def __init__(self, name: str = 'x') -> None:
            self.name = name

        async def __call__(self, ctx: TraitsContainer) -> int:
            counter.calls += 1
            return counter.calls

        async def render(self, ctx: TraitsContainer, value: int) -> str:
            return f'{self.name}{value}'

    @manager.register(call_key='gallery')
    @expression(docs=DOCS)
    class Gallery:
        """Returns a plain value; the renderer turns it into a fragment."""

        def __init__(self, path: str) -> None:
            self.path = path

        async def __call__(self, ctx: TraitsContainer) -> str:
            return self.path

        async def render(self, ctx: TraitsContainer, value: str) -> Image:
            return Image(value)

    @manager.register(call_key='bad_renderer')
    @expression(docs=DOCS)
    class BadRenderer:
        def __init__(self) -> None:
            pass

        async def __call__(self, ctx: TraitsContainer) -> int:
            return 1

        async def render(self, ctx: TraitsContainer, value: int) -> int:
            return value

    manager.freeze()
    return manager


CTX = TraitsContainer()


@pytest.mark.asyncio
async def test_text_only(manager: ExpressionsManager) -> None:
    result = await manager.evaluate('hello', CTX)
    assert result.parts == ('hello',)
    assert not result.has_fragments
    assert result.text == 'hello'


@pytest.mark.asyncio
async def test_empty_string(manager: ExpressionsManager) -> None:
    result = await manager.evaluate('', CTX)
    assert result.parts == ()
    assert result.text == ''


@pytest.mark.asyncio
async def test_escape_without_calls_is_unescaped(manager: ExpressionsManager) -> None:
    assert (await manager.evaluate('Price: $$5', CTX)).parts == ('Price: $5',)
    assert (await manager.evaluate('Price: $$5', CTX)).text == 'Price: $5'


@pytest.mark.asyncio
async def test_neighbouring_text_is_merged(manager: ExpressionsManager) -> None:
    result = await manager.evaluate('$upper(a)$upper(b) c', CTX)
    assert result.parts == ('AB c',)


@pytest.mark.asyncio
async def test_fragment_is_kept(manager: ExpressionsManager) -> None:
    result = await manager.evaluate('before $image(a.png) after', CTX)
    assert result.parts == ('before ', Image('a.png'), ' after')
    assert result.has_fragments


@pytest.mark.asyncio
async def test_neighbouring_fragments_are_not_merged(manager: ExpressionsManager) -> None:
    result = await manager.evaluate('$image(a.png)$break$image(b.png)', CTX)
    assert result.parts == (Image('a.png'), Break(), Image('b.png'))


@pytest.mark.asyncio
async def test_text_uses_fallbacks(manager: ExpressionsManager) -> None:
    text = 'see $image(a.png)$break!'
    assert (await manager.evaluate(text, CTX)).text == 'see [image a.png]!'


@pytest.mark.asyncio
async def test_renderer_can_return_fragment(manager: ExpressionsManager) -> None:
    result = await manager.evaluate('$gallery(a.png)', CTX)
    assert result.parts == (Image('a.png'),)


@pytest.mark.asyncio
async def test_renderer_must_return_text_or_fragment(manager: ExpressionsManager) -> None:
    with pytest.raises(ExpressionExecutionError) as exc_info:
        await manager.evaluate('$bad_renderer', CTX)
    assert isinstance(exc_info.value.__cause__, TypeError)


@pytest.mark.asyncio
async def test_expression_with_renderer_is_called_once(
    manager: ExpressionsManager, counter: Counter
) -> None:
    result = await manager.evaluate('$counted(a) $counted(b)', CTX)
    assert result.parts == ('a1 b2',)
    assert counter.calls == 2

    assert (await manager.evaluate('$counted(c)', CTX)).text == 'c3'
    call = result.decoded.decoded[0]
    assert isinstance(call, Call)
    assert await manager.execute_call(call, CTX, render=True) == 'a4'
    assert counter.calls == 4


@pytest.mark.asyncio
async def test_nested_fragment_is_passed_raw(manager: ExpressionsManager) -> None:
    result = await manager.evaluate('$path_of($image(a.png))', CTX)
    assert result.parts == ('a.png',)


@pytest.mark.asyncio
async def test_execute_call(manager: ExpressionsManager) -> None:
    call = (await manager.evaluate('$image(a.png)', CTX)).decoded.decoded[0]
    assert isinstance(call, Call)
    assert await manager.execute_call(call, CTX) == Image('a.png')
    assert await manager.execute_call(call, CTX, render=True) == '[image a.png]'


@pytest.mark.asyncio
async def test_ignore_errors(manager: ExpressionsManager) -> None:
    result = await manager.evaluate('a $fail b $image(x.png)', CTX, ignore_errors=True)
    assert result.parts == ('a  b ', Image('x.png'))
    assert len(result.errors) == 1
    assert isinstance(result.errors[0], ExpressionExecutionError)
    assert isinstance(result.errors[0].__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_errors_are_raised(manager: ExpressionsManager) -> None:
    with pytest.raises(ExpressionExecutionError):
        await manager.evaluate('a $fail', CTX)


DECODED = call_decoder.extract_calls('')


def test_result_merges_neighbouring_strings_and_drops_empty() -> None:
    result = EvaluationResult(
        parts=('', 'a', 'b', Image('x.png'), '', 'c', '', 'd', Break(), Break(), ''),
        decoded=DECODED,
    )
    assert result.parts == ('ab', Image('x.png'), 'cd', Break(), Break())


def test_result_parts_become_tuple() -> None:
    result = EvaluationResult(parts=['a', 'b'], decoded=DECODED)
    assert result.parts == ('ab',)
    assert isinstance(result.parts, tuple)


def test_result_rejects_other_types() -> None:
    with pytest.raises(TypeError):
        EvaluationResult(parts=('a', 1), decoded=DECODED)  # type: ignore[arg-type]


def test_result_errors_become_tuple() -> None:
    error = ExpressionExecutionError('x')
    assert EvaluationResult(parts=(), decoded=DECODED).errors == ()
    result = EvaluationResult(parts=(), decoded=DECODED, errors=[error])
    assert result.errors == (error,)
    assert isinstance(result.errors, tuple)


@pytest.mark.asyncio
async def test_call_result_render_without_renderer() -> None:
    assert await ExpressionCallResult(value=5, traits=CTX).render({}) == '5'
    result = ExpressionCallResult(value=Image('a.png'), traits=CTX)
    assert await result.render({}) == Image('a.png')


@pytest.mark.asyncio
async def test_call_result_render_with_renderer() -> None:
    received: list[Any] = []

    async def renderer(ctx: TraitsContainer, value: Any, di: Mapping[str, Any]) -> str:
        received.append((ctx, value, di))
        return f'<{value}>'

    di = {'service': object()}
    result = ExpressionCallResult(value=5, traits=CTX, renderer=renderer)
    assert await result.render(di) == '<5>'
    assert received == [(CTX, 5, di)]
