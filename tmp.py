import random

from packages.hubplatform.hubplatform.expressions.manager import ExpressionsManager
from packages.hubplatform.hubplatform.expressions.definition import expression
from packages.hubplatform.hubplatform.expressions.call_context import ExpressionContext
from packages.hubplatform.hubplatform.expressions.docs import ExpressionDocs


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
        print(int0, int1)
        print(type(int0), type(int1))
        self._min = min(int0, int1)
        self._max = max(int0, int1)


    async def __call__(self, ctx: ExpressionContext) -> int:
        return random.randint(self._min, self._max)

    async def render(self, ctx: ExpressionContext, value: int) -> str:
        return str(value)


manager.freeze()


async def main():
    text = 'Рандомное число: $random(NaN, Infinity).'
    result = await manager.format_string(text, ExpressionContext(), ignore_errors=False)
    print(result)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())