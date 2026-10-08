Expressions2 architecture
=========================

This package implements the proposed replacement independently of the existing
engine. It reuses expressions.syntax for parsing Call objects and template
strings. It changes no existing registry, application, component, or UI code.
The new application wiring remains an explicit future migration step.

The central idea is to separate three questions:

1. Which implementation exists? Answered by the catalog.
2. What does a template name mean here? Answered by a scope.
3. Which event data is available? Answered by typed capabilities in a runtime.

Those three questions have different identifiers. For example:

* funpay.order: unique implementation ID in the application's catalog.
* order: visible template alias, written as $order by a user.
* hubplatform.order_reference: shared capability containing an OrderReference.

An expression ID can contain namespace separators. A template alias follows
the existing ASCII letters/digits/underscore grammar. The ID funpay.order is
never interpreted as template syntax; a scope maps order to funpay.order.

What a capability means here
----------------------------

A capability is a named promise about one piece of available input. Its key
contains an ID and a value type; a runtime provides a value under that key::

    ORDER_REFERENCE = Capability('hubplatform.order_reference', OrderReference)
    FUNPAY_MESSAGE = Capability('funpay.message', FunPayMessage)

    runtime = ExpressionRuntime({
        FUNPAY_MESSAGE: original_native_message,
        ORDER_REFERENCE: OrderReference('funpay', extracted_order_id),
    })

The runtime has both pieces of data. The two objects do not inherit from one
another, and there is no FunPayOrderContext subclass. This is composition:
independent objects are assembled for a particular evaluation.

Keep the context concept if that vocabulary is useful. EvaluationContext is
still a context object. Its structure is a collection of declared data contracts
and a per-evaluation cache, rather than a growing hierarchy of event classes.

Capabilities can represent native marketplace data or small shared data. The
FunPay message contract intentionally exposes a FunPayMessage. The order
reference contract exposes only marketplace, order ID, and optional account ID.
An expression needing FunPay-specific message fields declares FUNPAY_MESSAGE.
A plugin needing order identity declares ORDER_REFERENCE.

This use of the word capability describes data availability. It does not implement
a security permission model. The key itself neither computes a value nor selects
an expression implementation. The component supplies the actual value explicitly.

A shared capability is a real common contract. Giving every component a named
capability containing its entire native context would preserve the original
coupling for plugins. The useful addition is the narrow OrderReference object,
which independent components can create without changing their native event APIs.

Two capabilities may deliberately share a value type. CURRENT_ORDER and
ORIGINAL_ORDER can both carry OrderReference. Nominal keys identify the role;
searching for an object by isinstance alone could not distinguish them.
Conflicting value types declared for the same key ID are rejected at setup.

Order identity and ownership
----------------------------

The shared OrderReference contract lives in contracts.py. Components construct
it at their expression/event boundary. They know where their native library keeps
the order ID. They normalize that ID to a string and use a stable marketplace name.
Plugins and components import the same contract rather than separately inventing
similar dataclasses or retrieving fields from arbitrary contexts.

The optional account_id is part of the identity. Supply it consistently when
multiple seller accounts can have overlapping order IDs. Plugin database writes
and reads must use identical identity fields. Human-facing marketplace names and
component display titles should not become persistence keys.

OrderReference makes no promise about an order's price, buyer, status, or shape.
Those can become additional shared contracts later if consumers need them. The
current architecture requires no common order event, common router, universal
marketplace component interface, or replacement of third-party library models.

The catalog
-----------

ExpressionCatalog belongs to one application/ExpressionsManager. Definitions have
globally unique IDs within that application, such as funpay.order, playerok.order,
and telegram_stars.amount. The catalog has no process-global singleton.

A definition contains a callable, required capability injection mapping, optional
renderer, and display metadata. It contains no assumptions about which template
name or component scope will expose it. One definition can be bound under several
aliases or used by several scopes.

Callbacks always receive EvaluationContext as their first parameter. Template
arguments follow it. Injected data occupies explicit keyword-only parameters::

    @manager.catalog.expression(
        'telegram_stars.amount', requires={'order': ORDER_REFERENCE}
    )
    async def stars_amount(ctx: EvaluationContext, *, order: OrderReference) -> int:
        row = await get_stars_row(ctx, order)
        return row.amount

requires serves two purposes: setup can verify the declared dependency, and
evaluation injects its typed value into the callback. Type hints help the Python
type checker; the Capability checks the supplied runtime object's type. Components
remain responsible for the semantic validity of IDs and data.

An expression may declare several capabilities, including capabilities introduced
by a plugin. There is no single context type attached to an expression registry.
Common utilities declare no capabilities, so no BaseContext class is necessary.

Injected parameter names are reserved. A template cannot supply order=... or replace
the first EvaluationContext parameter. Application services occupy ctx.services or
typed setup closures; they are never merged into user keyword arguments. Callback
parameter types are not automatically coerced from template values.

Ordinary sync functions, async functions, and initialized callable instances are
supported. Sync functions execute on the event loop and should perform only quick
work; use asynchronous database methods or explicitly offload blocking operations.
Classes are not implicitly constructed from template arguments.

Scopes and vocabulary composition
---------------------------------

A scope declares the input capabilities its event adapter promises, a map of
aliases to implementation IDs, optional tags, and one optional parent scope::

    manager.add_scope('common', bindings={'upper': 'hubplatform.upper'})
    manager.add_scope(
        'funpay.message', parent='common',
        provides={FUNPAY_MESSAGE}, bindings={'message': 'funpay.message'},
    )
    manager.add_scope(
        'funpay.order', parent='funpay.message',
        provides={ORDER_REFERENCE}, bindings={'order': 'funpay.order'},
    )

The child reuses its parent's vocabulary, tags, and input promises. This is a
relationship between template configurations. It creates no Python class
relationship between FunPay events or context objects.

The complete effective guarantee is checked before evaluating a template.
funpay.order therefore needs both FUNPAY_MESSAGE and ORDER_REFERENCE, even when
the template only calls $upper. A caller rendering an unrelated common template
should select common instead of claiming to render a FunPay sale.

Playerok can put its native order and ORDER_REFERENCE in playerok.order and inherit
only common. It does not acquire $message unless its chosen input actually
provides a message and the component deliberately binds a message implementation.
A component can have separate scopes for messages, orders, reviews, and other
template locations. A single component-wide scope would overpromise input data.

Scope declarations do not derive runtime values. The event adapter must supply
them. Additional runtime values do not change a scope's aliases or cause a plugin
to appear dynamically; the selected vocabulary stays fixed for that rendering.

How plugins attach expressions
------------------------------

The Telegram stars plugin registers one implementation per field. It then makes
one contribution based on the common input contract::

    manager.contribute(
        'telegram_stars.order_expressions',
        selector=Provides(ORDER_REFERENCE),
        bindings={
            'stars_amount': 'telegram_stars.amount',
            'telegram_transactionId': 'telegram_stars.telegram_transaction_id',
            'ton_transaction_id': 'telegram_stars.ton_transaction_id',
        },
    )

This contribution does not enumerate marketplace components. FunPay, Playerok,
or an independently installed new component receives it by declaring the shared
capability on a scope. A message scope without order identity does not receive it.

The plugin's sale event handlers remain specific to marketplace APIs. The FunPay
handler interprets a FunPay event, the Playerok handler interprets PlayerokNewOrder,
and both store a stars row under OrderReference. The expression implementations
know only the reference contract and the plugin repository API.

A future component can use the expression implementations unchanged. Someone
still needs to integrate that component's sale event with the plugin's database
writer, unless that integration is already available through another shared API.
Expression portability does not manufacture missing database rows.

Provides tests declared capability availability at setup, not the current order's
product type. An ordinary non-stars order can provide ORDER_REFERENCE too. The
example raises StarsOrderNotFoundError when there is no corresponding stars row.
It deliberately returns an empty string for an existing row whose transaction is
not available yet. A real plugin can choose a different display policy explicitly.
Render after awaited persistence when the reply depends on a freshly stored row.

Selectors can also combine Provides and Tagged with &, |, and ~. Tags describe
semantic placement, while capabilities describe input compatibility. Simple
capability selection is sufficient for the stars example.

Application setup and compilation
---------------------------------

Register definitions, scopes, services, and contributions in any order. Parent
scopes and implementation IDs may be forward references. Once every component
and plugin extension has installed, call manager.freeze().

Compilation checks:

* unique catalog, scope, service, and contribution IDs;
* consistent capability value types, including keys used in selectors;
* existing implementation and parent references;
* acyclic scope inheritance;
* input requirements of every bound expression;
* incompatible aliases in every effective scope.

Contributions apply to each flattened base scope independently. A negated selector
applied to a parent does not leak into a child that does not match. Contribution
selection cannot change the input guarantees that another selector observes.

Different definitions under one alias cause a configuration error. Importing the
same alias/definition twice is idempotent. A child can explicitly replace an
inherited alias using replace={'alias'}. Plugins should use explicit alternate
aliases when a short name would conflict; there is no registration-order priority.

The compiled result is published only after validation succeeds. Failure leaves
registration open for missing definitions to be supplied and compilation retried.
After successful freeze, public registration methods reject further writes.

"Future component" means a component registered later during setup or on a later
app startup. Live hot reload is not implemented. If needed, build a fresh manager,
freeze it completely, and replace the application's reference between requests.
Existing requests can continue using the old immutable compiled configuration.

Evaluation and lifetimes
------------------------

An event adapter constructs ExpressionRuntime from its native event, then calls::

    result = await manager.format_text('funpay.order', template, runtime)

The manager creates a fresh EvaluationContext for this call. It validates input,
parses the template, resolves nested calls to raw values, invokes the selected
implementations, and renders only results directly inserted into the output.
Generated text is not interpreted as a new template.

For $double($stars_amount()), the inner amount remains an int. A custom renderer
could display a standalone $stars_amount as "250 stars" while double still gets
250. Renderer callbacks receive (EvaluationContext, raw_value) and return str.
evaluate_call returns the raw value for programmatic use.

The three lifetimes are separate:

* Application: catalog, compiled scopes, and repository/service objects.
* Event input: native marketplace objects and their OrderReference.
* One rendering: EvaluationContext, resolved argument containers, and memo cache.

The stars lookup helper uses ctx.memoize with a namespaced key and the full order
reference. stars_amount and both transaction expressions reuse one fetched row
within a rendering. Another rendering fetches again, so updated transaction data
is visible and results cannot leak across orders or seller accounts.

Memoization is opt-in. Repeated $random or other nonmemoized expressions execute
independently. Concurrent requests for the same memo key share one task. Failed
lookups can be retried, recursive memo requests raise instead of deadlocking, and
unfinished lookup tasks are cancelled when the evaluation context closes.

Evaluation is sequential in template order. Independent renderings may execute
concurrently because their caches are separate. Domain service thread safety and
the stability of mutable native event objects remain responsibilities of callers.

Errors and documentation
------------------------

Configuration errors fail setup. Missing or wrong runtime capabilities fail before
any expression runs. Invalid public arguments, unknown aliases, custom domain
errors, and unexpected callback/renderer failures are evaluation errors. Original
Python exceptions remain attached as causes; errors retain scope, alias,
implementation identity when known, and the enclosing source span.

Strict rendering raises at the first failure. ignore_errors=True preserves the
exact original top-level expression text and returns errors alongside the output.
This flag does not suppress parser errors or repair missing scope input contracts.
No failed expression disappears silently from the generated message.

The existing parser and its syntax limitations are preserved. Internal catalog IDs
are never exposed as direct calls, and explicit aliases handle namespacing. This
implementation adds no eval/exec, attribute traversal syntax, or dynamic dispatch
based on the runtime object's Python class.

Documentation UIs should read manager.get_scope(scope_id).bindings to show visible
aliases and their actual selected implementations. Names, descriptions, categories,
and requirement metadata remain on each definition. Categories organize display;
they do not establish context inheritance or grant execution availability.

Package layout and adoption
---------------------------

* capabilities.py: typed keys, input runtime, evaluation context, memoization.
* contracts.py: the small shared OrderReference contract.
* catalog.py: implementation definitions, argument binding, and rendering.
* scopes.py: scope declarations, compiled bindings, and contribution selectors.
* engine.py: setup compilation, validation, and evaluation orchestration.
* defaults.py: common utilities with no marketplace data requirements.
* examples.py: runnable FunPay/Playerok composition and stars plugin integration.
* errors.py: configuration, context, argument, and execution error distinctions.

To adopt this in the existing app later, let the app own an ExpressionsManager,
register common utilities and component scopes during setup, install plugin
contributions during extension installation, and freeze after all installations.
Each native handler builds a runtime at its formatting boundary. Update expression
documentation menus to use the selected scope's bindings. The current package is
deliberately not wired into the old app by this implementation.

Start with explicit eager capability values and explicit memoized database reads.
Lazy capability providers, automatic dependency graphs, common marketplace events,
and live plugin reload can be added when needed. None is required to solve the
marketplace/context/Telegram stars problem described here.
