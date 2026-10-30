import random

from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression
from hubplatform.expressions.call_context import ExpressionContext
from hubplatform.expressions.docs import ExpressionDocs


manager = ExpressionsManager({})


manager.add_context(ExpressionContext, 'root')


@manager.register(
    context_type=ExpressionContext,
    call_key='random',
    category='math',
)
@expression(docs=ExpressionDocs(overview='random overview'))
class RandomExpression:
    def __init__(self, int0: int, int1: int) -> None:
        self._min = min(int0, int1)
        self._max = max(int0, int1)

    async def __call__(self, ctx: ExpressionContext) -> int:
        return random.randint(self._min, self._max)

    async def render(self, ctx: ExpressionContext, value: int) -> str:
        return str(value)


manager.freeze()


async def main():
    text = 'Рандомное число: $random($random(1, 100), $random(1000, 2000)).'
    result = await manager.format_string(text, ExpressionContext(), ignore_errors=False)
    print(result)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())