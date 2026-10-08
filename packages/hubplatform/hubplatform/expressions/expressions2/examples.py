"""Runnable example: two native event models, one component-independent plugin.

Run with the workspace Python environment::

    python -m hubplatform.expressions.expressions2.examples

These small fake marketplace models make the architecture executable without
real accounts, network access, or a database. Replace the two event adapters
with the corresponding component's native event handler code. Keep the plugin
expressions unchanged when another component provides ORDER_REFERENCE.
"""

from __future__ import annotations

import asyncio
from typing import Protocol
from dataclasses import dataclass

from .engine import ExpressionsManager
from .errors import ExpressionError
from .scopes import Provides
from .defaults import register_common
from .contracts import ORDER_REFERENCE, OrderReference
from .capabilities import Capability, EvaluationContext, ExpressionRuntime


@dataclass(frozen=True)
class FunPayMessage:
    """A fake native message with sale information embedded in its body."""

    text: str


@dataclass(frozen=True)
class PlayerokNewOrder:
    """A fake third-party event whose order is represented directly."""

    id: int
    title: str


FUNPAY_MESSAGE = Capability('funpay.message', FunPayMessage)
PLAYEROK_ORDER = Capability('playerok.native_order', PlayerokNewOrder)


def funpay_order_id(message: FunPayMessage) -> str:
    """Simulate the component-specific interpretation of a sale message."""
    # This parsing belongs to the FunPay component. The expression engine and
    # the stars expressions never learn that a FunPay order was a message.
    if not message.text.startswith('SALE '):
        raise ValueError('This FunPay message does not describe a sale.')
    return message.text.split()[1]


def funpay_sale_runtime(message: FunPayMessage) -> ExpressionRuntime:
    """Compose raw FunPay data and the small shared order identity contract."""
    return ExpressionRuntime(
        {
            FUNPAY_MESSAGE: message,
            ORDER_REFERENCE: OrderReference('funpay', funpay_order_id(message)),
        }
    )


def playerok_sale_runtime(order: PlayerokNewOrder) -> ExpressionRuntime:
    """Adapt a different native shape to the same shared identity contract."""
    return ExpressionRuntime(
        {
            PLAYEROK_ORDER: order,
            ORDER_REFERENCE: OrderReference('playerok', str(order.id)),
        }
    )


def register_funpay(manager: ExpressionsManager) -> None:
    """Declare FunPay implementations and its message/sale template vocabularies."""

    @manager.catalog.expression('funpay.message', requires={'message': FUNPAY_MESSAGE})
    def message_text(ctx: EvaluationContext, *, message: FunPayMessage) -> str:
        return message.text

    @manager.catalog.expression('funpay.order', requires={'message': FUNPAY_MESSAGE})
    def order_id(ctx: EvaluationContext, *, message: FunPayMessage) -> str:
        return funpay_order_id(message)

    manager.add_scope(
        'funpay.message',
        parent='common',
        provides={FUNPAY_MESSAGE},
        bindings={'message': 'funpay.message'},
        tags={'marketplace'},
    )
    manager.add_scope(
        'funpay.order',
        parent='funpay.message',
        provides={ORDER_REFERENCE},
        bindings={'order': 'funpay.order'},
    )


def register_playerok(manager: ExpressionsManager) -> None:
    """Reuse $order while preserving Playerok's native type and semantics."""

    @manager.catalog.expression('playerok.order', requires={'order': PLAYEROK_ORDER})
    def order_id(ctx: EvaluationContext, *, order: PlayerokNewOrder) -> int:
        return order.id

    manager.add_scope(
        'playerok.order',
        parent='common',
        provides={PLAYEROK_ORDER, ORDER_REFERENCE},
        bindings={'order': 'playerok.order'},
        tags={'marketplace'},
    )


@dataclass(frozen=True)
class StarsRecord:
    """The plugin's own database record, shared by its expressions."""

    amount: int
    telegram_transaction_id: str | None
    ton_transaction_id: str | None


class StarsRepository(Protocol):
    """The plugin's storage API; implementations can use any database."""

    async def find(self, reference: OrderReference) -> StarsRecord | None:
        """Find a record stored by one of the plugin's native event handlers."""
        ...


class StarsOrderNotFoundError(ExpressionError):
    """A known order has no stars record, including a not-yet-processed sale."""


def register_stars(manager: ExpressionsManager, repository: StarsRepository) -> None:
    """Install a plugin without importing or enumerating marketplace components.

    The repository is captured during setup. In real plugins, marketplace-specific
    sale handlers write records keyed by OrderReference before these templates
    are rendered. Those handlers remain separate integrations with native APIs.
    """

    async def record_for(ctx: EvaluationContext, order: OrderReference) -> StarsRecord:
        # All three expressions reuse this row within one rendering. The key
        # includes the full identity, including account_id when supplied.
        record = await ctx.memoize(
            ('telegram_stars.order_record', order), lambda: repository.find(order)
        )
        if record is None:
            raise StarsOrderNotFoundError(
                f'No Telegram stars record for {order.marketplace}:{order.order_id}.'
            )
        return record

    @manager.catalog.expression(
        'telegram_stars.amount', requires={'order': ORDER_REFERENCE}, category='telegram_stars'
    )
    async def stars_amount(ctx: EvaluationContext, *, order: OrderReference) -> int:
        return (await record_for(ctx, order)).amount

    @manager.catalog.expression(
        'telegram_stars.telegram_transaction_id', requires={'order': ORDER_REFERENCE}
    )
    async def telegram_transaction_id(ctx: EvaluationContext, *, order: OrderReference) -> str:
        # An unsent transaction has a deliberately chosen display value. A missing
        # stars order is a separate error and must not be mistaken for this state.
        return (await record_for(ctx, order)).telegram_transaction_id or ''

    @manager.catalog.expression(
        'telegram_stars.ton_transaction_id', requires={'order': ORDER_REFERENCE}
    )
    async def ton_transaction_id(ctx: EvaluationContext, *, order: OrderReference) -> str:
        return (await record_for(ctx, order)).ton_transaction_id or ''

    manager.contribute(
        'telegram_stars.order_expressions',
        selector=Provides(ORDER_REFERENCE),
        bindings={
            'stars_amount': 'telegram_stars.amount',
            'telegram_transactionId': 'telegram_stars.telegram_transaction_id',
            'ton_transaction_id': 'telegram_stars.ton_transaction_id',
        },
    )


class MemoryStarsRepository:
    """Fake storage with an observable lookup count for the example and tests."""

    def __init__(self) -> None:
        self.rows: dict[OrderReference, StarsRecord] = {}
        self.lookups: list[OrderReference] = []

    async def find(self, reference: OrderReference) -> StarsRecord | None:
        self.lookups.append(reference)
        return self.rows.get(reference)


async def demo() -> tuple[str, str, int]:
    """Render both marketplace sales and return their text and total lookup count."""
    manager = ExpressionsManager()
    repository = MemoryStarsRepository()

    # Plugin registration intentionally precedes component registration. A
    # future third-party component opts in simply by providing ORDER_REFERENCE.
    register_stars(manager, repository)
    register_funpay(manager)
    register_playerok(manager)
    register_common(manager)
    manager.freeze()

    repository.rows[OrderReference('funpay', 'FP-42')] = StarsRecord(250, 'tg-fp', 'ton-fp')
    repository.rows[OrderReference('playerok', '73')] = StarsRecord(500, 'tg-po', 'ton-po')

    template = '$order() / $stars_amount() / $telegram_transactionId() / $ton_transaction_id()'
    funpay = await manager.format_text(
        'funpay.order', template, funpay_sale_runtime(FunPayMessage('SALE FP-42 Telegram stars'))
    )
    playerok = await manager.format_text(
        'playerok.order', template, playerok_sale_runtime(PlayerokNewOrder(73, 'Telegram stars'))
    )
    return funpay.result_text, playerok.result_text, len(repository.lookups)


if __name__ == '__main__':
    # Keep the example's core callable from tests without console output.
    output = asyncio.run(demo())
    for line in output:
        print(line)  # noqa: T201
