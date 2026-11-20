from __future__ import annotations

from typing import Any

import pytest
from hubplatform.expressions.docs import ExpressionDocs
from hubplatform.expressions.traits import Trait, TraitsView, TraitsContainer
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression
from hubplatform.expressions.exceptions import (
    UndeclaredTraitError,
    UnknownExpressionError,
    AmbiguousExpressionError,
    ExpressionExecutionError,
    ExpressionsConfigurationError,
)
from hubplatform.expressions.requirement import Requirement


DOCS = ExpressionDocs(name='test', overview='test')


class OrderTrait(Trait, name='order', description='order'):
    order_id: str = '1'


class FunPayOrderTrait(OrderTrait, name='funpay order', description='funpay order'):
    pass


class G2GOrderTrait(OrderTrait, name='g2g order', description='g2g order'):
    pass


class ReviewTrait(Trait, name='review', description='review'):
    text: str = 'nice'


class InitiatorTrait(Trait, name='initiator', description='initiator'):
    username: str = 'bob'


ALL_TRAITS: dict[str, type[Trait]] = {
    'order': OrderTrait,
    'funpay_order': FunPayOrderTrait,
    'g2g_order': G2GOrderTrait,
    'review': ReviewTrait,
    'initiator': InitiatorTrait,
}


def returns(value: str, requires: Any = ()) -> Any:
    @expression(docs=DOCS, requires=requires)
    async def inner(traits: TraitsContainer) -> str:
        return value

    return inner


def make_manager() -> ExpressionsManager:
    manager = ExpressionsManager({})
    for trait_id, trait_type in ALL_TRAITS.items():
        manager.add_trait(trait_type, trait_id)
    return manager


async def evaluate(manager: ExpressionsManager, text: str, *traits: Trait) -> str:
    return (await manager.evaluate(text, TraitsContainer(*traits))).text


class TestTraits:
    def test_name_and_description_are_required(self) -> None:
        with pytest.raises(ValueError):

            class NoName(Trait, description='d'):
                pass

        with pytest.raises(ValueError):

            class NoDescription(Trait, name='n'):
                pass

    def test_name_and_description_are_stored(self) -> None:
        assert OrderTrait.name == 'order'
        assert FunPayOrderTrait.description == 'funpay order'


class TestContainer:
    def test_getitem_resolves_subclasses(self) -> None:
        funpay_order = FunPayOrderTrait(order_id='5')
        container = TraitsContainer(InitiatorTrait(), funpay_order)
        assert container[OrderTrait] is funpay_order
        assert container[FunPayOrderTrait] is funpay_order

    def test_getitem_returns_first_match(self) -> None:
        first, second = FunPayOrderTrait(order_id='1'), G2GOrderTrait(order_id='2')
        container = TraitsContainer(first, second)
        assert container[OrderTrait] is first
        assert container[G2GOrderTrait] is second
        assert container.get_all_traits(OrderTrait) == (first, second)
        assert container.get_all_traits(ReviewTrait) == ()

    def test_missing_trait(self) -> None:
        container = TraitsContainer(OrderTrait())
        with pytest.raises(KeyError):
            container[ReviewTrait]
        assert container.get(ReviewTrait) is None
        assert container.get(ReviewTrait, 'default') == 'default'
        assert ReviewTrait not in container
        assert OrderTrait in container

    def test_shape(self) -> None:
        container = TraitsContainer(FunPayOrderTrait(), InitiatorTrait(), InitiatorTrait())
        expected: set[type[Trait]] = {FunPayOrderTrait, InitiatorTrait}
        assert container.shape == expected
        assert len(container) == 3
        assert TraitsContainer().shape == frozenset()

    def test_rejects_non_traits(self) -> None:
        with pytest.raises(TypeError):
            TraitsContainer('not a trait')  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            TraitsContainer().get(int)  # type: ignore[type-var]

    def test_view_answers_only_for_declared_traits(self) -> None:
        funpay_order, initiator = FunPayOrderTrait(), InitiatorTrait()
        view = TraitsContainer(funpay_order, initiator, ReviewTrait()).view([FunPayOrderTrait])

        assert isinstance(view, TraitsView)
        assert view[FunPayOrderTrait] is funpay_order
        assert view[OrderTrait] is funpay_order
        assert view.traits == (funpay_order,)
        assert InitiatorTrait not in view
        with pytest.raises(UndeclaredTraitError):
            view[InitiatorTrait]
        with pytest.raises(UndeclaredTraitError):
            view.get_all_traits(ReviewTrait)

    def test_view_of_base_type_does_not_allow_subclasses(self) -> None:
        view = TraitsContainer(FunPayOrderTrait()).view([OrderTrait])
        assert isinstance(view[OrderTrait], FunPayOrderTrait)
        with pytest.raises(UndeclaredTraitError):
            view[FunPayOrderTrait]


class TestRequirement:
    def test_minimal_form(self) -> None:
        assert Requirement(FunPayOrderTrait, OrderTrait).traits == (FunPayOrderTrait,)
        assert Requirement(OrderTrait, OrderTrait).traits == (OrderTrait,)
        assert Requirement().is_empty

    def test_order_does_not_matter(self) -> None:
        a = Requirement(OrderTrait, InitiatorTrait)
        b = Requirement(InitiatorTrait, OrderTrait)
        assert a == b
        assert hash(a) == hash(b)

    def test_of(self) -> None:
        assert Requirement.of(OrderTrait) == Requirement(OrderTrait)
        assert Requirement.of([OrderTrait, ReviewTrait]) == Requirement(ReviewTrait, OrderTrait)
        assert Requirement.of(()) == Requirement()

    def test_rejects_non_traits(self) -> None:
        with pytest.raises(TypeError):
            Requirement(int)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            Requirement(Trait)

    def test_is_satisfied_by(self) -> None:
        requirement = Requirement(OrderTrait, InitiatorTrait)
        assert requirement.is_satisfied_by({FunPayOrderTrait, InitiatorTrait})
        assert not requirement.is_satisfied_by({FunPayOrderTrait})
        assert Requirement(FunPayOrderTrait).is_satisfied_by({FunPayOrderTrait})
        assert not Requirement(FunPayOrderTrait).is_satisfied_by({OrderTrait})
        assert Requirement().is_satisfied_by(set())

    def test_specificity(self) -> None:
        empty = Requirement()
        order = Requirement(OrderTrait)
        funpay = Requirement(FunPayOrderTrait)
        order_initiator = Requirement(OrderTrait, InitiatorTrait)
        review = Requirement(ReviewTrait)

        assert order.is_more_specific_than(empty)
        assert funpay.is_more_specific_than(order)
        assert order_initiator.is_more_specific_than(order)
        assert not order.is_more_specific_than(order)
        assert not order.is_more_specific_than(review)
        assert not review.is_more_specific_than(order)
        assert not funpay.is_more_specific_than(order_initiator)
        assert not order_initiator.is_more_specific_than(funpay)

    def test_union(self) -> None:
        union = Requirement(OrderTrait) | Requirement(FunPayOrderTrait, ReviewTrait)
        assert union == Requirement(FunPayOrderTrait, ReviewTrait)


class TestResolution:
    @pytest.mark.asyncio
    async def test_expression_receives_view(self) -> None:
        manager = make_manager()
        received: list[TraitsContainer] = []

        @manager.register(call_key='order_id')
        @expression(docs=DOCS, requires=OrderTrait)
        async def order_id(traits: TraitsContainer) -> str:
            received.append(traits)
            return traits[OrderTrait].order_id

        @manager.register(call_key='peek')
        @expression(docs=DOCS, requires=OrderTrait)
        async def peek(traits: TraitsContainer) -> str:
            return traits[InitiatorTrait].username

        manager.freeze()
        result = await evaluate(
            manager, '$order_id', FunPayOrderTrait(order_id='7'), InitiatorTrait()
        )
        assert result == '7'
        assert isinstance(received[0], TraitsView)
        assert InitiatorTrait not in received[0]

        with pytest.raises(ExpressionExecutionError) as exc_info:
            await evaluate(manager, '$peek', OrderTrait(), InitiatorTrait())
        assert isinstance(exc_info.value.__cause__, UndeclaredTraitError)

    @pytest.mark.asyncio
    async def test_availability(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('u'), 'upper')
        manager.add_expression(returns('order', OrderTrait), 'order_id')
        manager.add_expression(returns('fp', FunPayOrderTrait), 'order_link')
        manager.add_expression(returns('both', (OrderTrait, InitiatorTrait)), 'greeting')
        manager.freeze()

        assert await evaluate(manager, '$upper') == 'u'
        assert await evaluate(manager, '$order_id', G2GOrderTrait()) == 'order'
        assert await evaluate(manager, '$order_link', FunPayOrderTrait()) == 'fp'
        assert await evaluate(manager, '$greeting', OrderTrait(), InitiatorTrait()) == 'both'

        for text, traits in [
            ('$order_id', ()),
            ('$order_link', (G2GOrderTrait(),)),
            ('$order_link', (OrderTrait(),)),
            ('$greeting', (OrderTrait(),)),
        ]:
            with pytest.raises(UnknownExpressionError):
                await evaluate(manager, text, *traits)

    @pytest.mark.asyncio
    async def test_subclass_override_wins(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('generic', OrderTrait), 'order_id')
        manager.add_expression(returns('fp', FunPayOrderTrait), 'order_id', override=True)
        manager.freeze()

        assert await evaluate(manager, '$order_id', FunPayOrderTrait()) == 'fp'
        assert await evaluate(manager, '$order_id', G2GOrderTrait()) == 'generic'
        assert await evaluate(manager, '$order_id', OrderTrait()) == 'generic'

    @pytest.mark.asyncio
    async def test_superset_override_wins(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('order', OrderTrait), 'x')
        manager.add_expression(
            returns('order+user', (OrderTrait, InitiatorTrait)), 'x', override=True
        )
        manager.freeze()

        assert await evaluate(manager, '$x', OrderTrait()) == 'order'
        assert await evaluate(manager, '$x', OrderTrait(), InitiatorTrait()) == 'order+user'

    @pytest.mark.asyncio
    async def test_ambiguous_call_raises_at_runtime(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('order', OrderTrait), 'x')
        manager.add_expression(returns('review', ReviewTrait), 'x')
        manager.freeze()

        assert len(manager.warnings) == 1
        assert await evaluate(manager, '$x', OrderTrait()) == 'order'
        assert await evaluate(manager, '$x', ReviewTrait()) == 'review'
        with pytest.raises(AmbiguousExpressionError) as exc_info:
            await evaluate(manager, '$x', OrderTrait(), ReviewTrait())
        assert {i.requirement for i in exc_info.value.candidates} == {
            Requirement(OrderTrait),
            Requirement(ReviewTrait),
        }

    @pytest.mark.asyncio
    async def test_covering_override_resolves_ambiguity(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('order', OrderTrait), 'x')
        manager.add_expression(returns('review', ReviewTrait), 'x')
        manager.add_expression(returns('both', (OrderTrait, ReviewTrait)), 'x', override=True)
        manager.freeze()

        assert manager.warnings == ()
        assert await evaluate(manager, '$x', OrderTrait(), ReviewTrait()) == 'both'

    def test_subclass_and_superset_are_ambiguous(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('order', OrderTrait), 'x')
        manager.add_expression(returns('fp', FunPayOrderTrait), 'x', override=True)
        manager.add_expression(returns('user', (OrderTrait, InitiatorTrait)), 'x', override=True)
        manager.freeze()

        assert len(manager.warnings) == 1
        scope = manager.get_scope([FunPayOrderTrait, InitiatorTrait])
        assert 'x' in scope.ambiguous
        assert 'x' not in scope.expressions

    def test_scope_is_cached_by_shape(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('order', OrderTrait), 'order_id')
        manager.freeze()

        scope = manager.get_scope(TraitsContainer(OrderTrait(), OrderTrait()))
        assert scope is manager.get_scope([OrderTrait])
        assert set(scope.expressions) == {'order_id'}
        assert scope.shape == frozenset({OrderTrait})

    def test_get_scope_rejects_non_traits(self) -> None:
        manager = make_manager()
        manager.freeze()
        with pytest.raises(TypeError):
            manager.get_scope([int])  # type: ignore[list-item]


class TestConfiguration:
    def test_override_without_flag_is_an_error(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('generic', OrderTrait), 'x')
        manager.add_expression(returns('fp', FunPayOrderTrait), 'x')
        with pytest.raises(ExpressionsConfigurationError, match='override=True'):
            manager.freeze()
        assert not manager.frozen

    def test_override_flag_without_overridden_is_an_error(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('fp', FunPayOrderTrait), 'x', override=True)
        with pytest.raises(ExpressionsConfigurationError, match='no less specific'):
            manager.freeze()

    def test_unregistered_trait_is_an_error(self) -> None:
        class UnregisteredTrait(Trait, name='u', description='u'):
            pass

        manager = make_manager()
        manager.add_expression(returns('u', UnregisteredTrait), 'x')
        with pytest.raises(ExpressionsConfigurationError, match='not registered'):
            manager.freeze()

    def test_same_requirement_twice_is_an_error(self) -> None:
        manager = make_manager()
        manager.add_expression(returns('a', (OrderTrait, ReviewTrait)), 'x')
        with pytest.raises(ValueError):
            manager.add_expression(returns('b', (ReviewTrait, OrderTrait)), 'x')

    def test_add_trait_checks(self) -> None:
        manager = make_manager()
        with pytest.raises(ValueError):
            manager.add_trait(OrderTrait, 'other_id')

        class OtherTrait(Trait, name='o', description='o'):
            pass

        with pytest.raises(ValueError):
            manager.add_trait(OtherTrait, 'order')
        with pytest.raises(TypeError):
            manager.add_trait(Trait, 'trait')

    def test_traits_are_listed_in_registration_order(self) -> None:
        manager = make_manager()
        assert list(manager.traits) == list(ALL_TRAITS)
        assert manager.get_trait_id(FunPayOrderTrait) == 'funpay_order'

    def test_merge(self) -> None:
        a = ExpressionsManager({})
        a.add_trait(OrderTrait, 'order')
        a.add_expression(returns('generic', OrderTrait), 'x')
        b = ExpressionsManager({})
        b.add_trait(FunPayOrderTrait, 'funpay_order')
        b.add_expression(returns('fp', FunPayOrderTrait), 'x', override=True)

        manager = ExpressionsManager({})
        manager.merge_from(a, b, skip_existing=False)
        assert {i.requirement for i in manager.get_registrations('x')} == {
            Requirement(OrderTrait),
            Requirement(FunPayOrderTrait),
        }
        assert list(manager.traits) == ['order', 'funpay_order']

        conflicting = ExpressionsManager({})
        conflicting.add_expression(returns('other', OrderTrait), 'x')
        with pytest.raises(RuntimeError):
            manager.merge_from(conflicting, skip_existing=False)
