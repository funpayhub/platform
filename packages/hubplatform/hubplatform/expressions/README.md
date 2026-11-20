# Expressions

## Purpose
Expressions allow embedding evaluated values in string literals.

## Syntax
- Expressions can be embedded in strings using the `$` syntax: `$expression`.
- An expression name may contain only ASCII letters, digits and `_`. Unlike Python identifiers, it may
  start with a digit: `$1st_place` and `$5` are the expressions named `1st_place` and `5`.
  Example: `$expression1()`.
- An expression name ends at the first character that is not an ASCII letter, digit or `_`
  (i.e. not in `[a-zA-Z0-9_]`). That character is not part of the expression:
  `Hello, $username!` is the `$username` expression followed by the text `!`.
- Expressions can accept arguments enclosed in parentheses `()`:
  `$expression(1, 123.321, "some_string", flag=true)`.
  Arguments must be separated by a comma (`,`). Trailing commas are not allowed.
- The opening `(` of the argument list must immediately follow the expression name.
  No whitespace is allowed between them: `$expression (1)` is the `$expression` expression
  without arguments, followed by the text ` (1)`.
- `$expression` and `$expression()` are equivalent.
- Arguments can be positional or keyword (`name=value`):
  - A keyword argument name can be any valid Python identifier (`str.isidentifier()`) except a Python
    keyword (`keyword.iskeyword()`: `class`, `if`, `None`, ...). Unlike expression names, it may contain
    non-ASCII letters, and it cannot start with a digit. Names that are not reserved keywords are
    allowed, including `match`, `type`, `print`, `true` and `null`.
  - A keyword argument name is normalized to Unicode NFKC before it is checked, the same way Python
    normalizes identifiers in source code, and the expression receives the normalized name. For example,
    `ℌ=1` is passed as `H=1`, and the fullwidth `ｉｆ=1` becomes `if`, which is a keyword and a syntax
    error. Normalization is applied before the keyword and duplicate checks.
  - A keyword argument value can be of any supported type, including another expression call.
  - Positional arguments must come before keyword arguments, and a keyword name
    must not be repeated. Names are compared after normalization: `ℌ=1, H=2` is a duplicate.
- Inside an argument list, whitespace around separators and brackets is allowed and is not part of the values:
  `$expression( a , b )` is the same as `$expression(a,b)`. Whitespace inside an unquoted
  string is kept: `$expression(hello world)` receives `hello world`. To keep leading or
  trailing whitespace, enclose the string in double quotes: `" a "`.
- An expression can be passed as an argument to another expression.
  In this case, the result of the passed expression is not converted to a string,
  but is passed directly to the receiving expression.
- The result of an expression is inserted into the text as-is and is never parsed again:
  a `$` in the result is neither an expression nor an escape.
- To separate an expression from text that starts with a name character (`[a-zA-Z0-9_]`),
  use an empty argument list: `Order status: $order_status()ed.`

### Escaping
- A literal `$` in text must always be escaped as `$$`: `Price: $$5` is rendered as `Price: $5`.
- A lone `$` is never treated as literal text. A `$` that is neither part of `$$` nor followed
  by a valid expression name is a syntax error. For example, `$ `, `$!` and a trailing `$` are
  errors. `$5` is not an error in the syntax: it is a call of the expression named `5`, so a literal
  `$5` must be written as `$$5`.
- `$$` is processed first, from left to right:
  - `$$name` is rendered as `$name`;
  - `$$$name` is rendered as `$` followed by the value of the `$name` expression.
- Escaping applies only to the text of a string. Inside quoted string arguments `$` has no
  special meaning and is passed as-is: `$expression("cost: $5")` receives the string `cost: $5`.

### Argument types
Expressions can accept values of any type, including values returned by other expressions.
However, the syntax for passing arguments directly is defined only for the following types:

- **Integers**: an optional leading `-` followed by digits, without leading zeros
  (regex: `-?(0|[1-9][0-9]*)`).
  Examples: `0`, `123`, `-5`.
- **Floats**: an optional leading `-`, an integer part without leading zeros, and a fractional part,
  an exponent, or both. The fractional part is a decimal point (`.`) followed by at least one digit.
  The exponent is `e` or `E`, an optional sign (`+` or `-`) and at least one digit
  (regex: `-?(0|[1-9][0-9]*)(\.[0-9]+([eE][+-]?[0-9]+)?|[eE][+-]?[0-9]+)`).
  Examples: `123.321`, `-0.5`, `10.0`, `1e5`, `1.5E3`, `1e+16`, `1e-07`.
- Any other numeric-looking value is a string, not a number: for example `007`, `01e5`, `1.`, `.5`,
  `1.e5`, `.5e1`, `1e`, `1e+`, `+1`, `NaN`, `Infinity` and `-Infinity` are all strings.
- **Booleans**: `true` or `false`, case-sensitive.
- **Null**: `null`, case-sensitive (as in JSON).
- **Strings**: can be written without quotes if they contain no characters from the set
  `[](){}:=,$\"`. Whitespace inside an unquoted string is allowed and kept, but leading and
  trailing whitespace is ignored: `$expression( two words )` receives `two words`.
  Strings that contain characters from the set above, are empty, or have leading or
  trailing whitespace must be enclosed in double quotes (`"`).
  A quoted string follows JSON string syntax. A backslash starts an escape sequence, and only
  these are valid: `\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`, `\t` and `\uXXXX`. Any other
  backslash sequence is a syntax error, so a literal backslash must be doubled: `"C:\\path"`.
  Raw control characters (U+0000 to U+001F, including a newline and a tab) are allowed inside
  quotes and are kept as-is; `\n`, `\t` and so on are equivalent. Escape sequences are not processed
  in unquoted strings, where a backslash is simply not allowed.
  If an unquoted value (with its leading and trailing whitespace removed) matches the syntax of
  another supported type, it is interpreted as that type.
  For example, `123` is interpreted as an integer, not a string. To represent it as a string, write `"123"`.
  The same applies to `true`, `false` and `null`.
  Examples: `some_string`, `"quoted string"`.
- **Sequences**: written using square brackets `[]`. An empty sequence `[]` is allowed.
  Can contain values of any supported type, including nested sequences, mappings and other expression calls.
  Values must be separated by a comma. Trailing commas are not allowed.
  Example: `[123, "123", [nested, list], [[true, false]]]`
- **Mappings**: written using braces `{}`. An empty mapping `{}` is allowed.
  Key-value pairs must be separated with `:`, pairs with a comma. Trailing commas are not allowed.
  Keys can be a value of any supported type, including sequences, mappings and expression calls,
  because a decoded sequence is a tuple, a decoded mapping is a `frozendict`, and a call is immutable,
  so all of them are hashable. A key written with such a value can contain only values that are
  hashable too, and that is always the case for the syntax above: for example,
  `{[1, 2]: a, {x: [3]}: b, $call(1): c}`.
  Duplicate keys are not allowed and cause a parsing error.
  Keys are compared the same way as Python `dict` keys: values that are equal in Python are the
  same key. In particular, `1`, `1.0` and `true` are equal, as are `0`, `0.0` and `false`.
  So `{1: a, true: b}` and `{0: a, 0.0: b}` are duplicate-key errors, while `{1: a, "1": b}` is valid,
  because the string `"1"` is not equal to the integer `1`.
  The same rule applies to keys that are sequences and mappings, compared element by element:
  `{[1]: a, [true]: b}` and `{{1: x}: a, {true: x}: b}` are duplicate-key errors, `{[]: a, {}: b}` is valid
  because an empty sequence is not equal to an empty mapping, and so are `{[1]: a, [[1]]: b}` and
  `{[1]: a, ["1"]: b}`.
  Calls are compared by their written form, the name and the arguments, and duplicates are detected
  while parsing, before any expression is evaluated: `{$a: x, $a(): y}` is a duplicate-key error
  (`$a` and `$a()` are the same call), and `{$a(1): x, $a(2): y}` is valid.
  Values can be of any supported type, including nested sequences, mappings and other expression calls.
  Example: `{some_key: 123, 1000: {another: mapping}, "some call": $other_expression(123, arg2)}`

## Implementation

> Code examples show the current API. Parts marked **(planned)** describe the target design that is
> not implemented yet; their examples are pseudocode.

### Overview
A text is evaluated with a **container of traits**. A trait is a small piece of data: an order,
a message, the user who did something, ... Each expression declares the trait types it needs and
is available for every container that has them. If several expressions with the same name are
available, the most specific one wins.

The system consists of the following parts:

1. `Trait` (`hubplatform.expressions.traits`) - the base class of all traits. A trait is a pydantic
   model with a name and a description, which the documentation UI shows.
2. `TraitsContainer` - the traits a text is evaluated with. Handlers create it.
3. `Requirement` (`hubplatform.expressions.requirement`) - the set of trait types an expression
   needs.
4. `ExpressionDefinition` - an expression function together with its documentation, its requirement
   and an optional renderer. Created by the `@expression` decorator.
5. `ExpressionsScope` - the expressions available for one container shape, with overrides already
   resolved. Scopes are computed and cached by the manager.
6. `ExpressionsManager` - an orchestrator that owns all traits and expressions, validates them,
   resolves names and renders texts.

### Traits
```python
class OrderTrait(Trait, name=I18nString(...), description=I18nString(...)):
    order_id: str                                      # normalized, cross-marketplace form
    order_name: str
    order_amount: int


class FunPayOrderTrait(OrderTrait, name=..., description=...):  # a FunPay order IS an order
    order: funpay.Order                                # native object with native types


class InitiatorTrait(Trait, name=..., description=...):  # the user is a separate trait
    initiator_id: str
    initiator_username: str
```

Rules:

- **Inheritance means "is a".** A trait inherits from another trait only when it really is one:
  `FunPayOrderTrait(OrderTrait)`. A trait never inherits from another one just to share fields.
  Data about another entity (the user who made the order, the order a review is about) is a
  separate trait in the same container.
- **Generic traits.** The traits shared by every marketplace (`InitiatorTrait`, `OrderTrait`,
  `ReviewTrait`, `MessageTrait`, ...) are defined in one place: `hubplatform.app.expressions`.
  They are plain data classes with normalized fields that every marketplace can provide, so a
  handler can use them directly. Marketplace components and plugins refine them by subclassing
  and do not define parallel generic traits.
- **Field types are never changed in subclasses.** Required generic fields are filled by the
  subclass in their normalized form (`order_id=str(order.id)`). Data that not every marketplace
  provides is optional (`None` by default). Marketplace-specific data with native types is stored
  in extra fields, usually as the native object itself (`FunPayOrderTrait.order`), and is used by
  marketplace-specific expressions.
- **Expensive data.** Data that has to be fetched is exposed as an `async` method with a default
  implementation in the generic trait (for example, returning `None`). Subclasses override it
  and cache the result.
- **Registration.** Every trait type that an expression requires must be registered with
  `manager.add_trait(trait_type, id)`. Registered traits are the filters of the documentation UI,
  and their IDs are stored in its callback data.

### Containers
```python
traits = TraitsContainer(
    FunPayOrderTrait(order_id='123', order_name='Gold', order_amount=5, order=order),
    InitiatorTrait(initiator_id='42', initiator_username='bob'),
)
traits[OrderTrait]                 # the FunPayOrderTrait: subclasses are resolved
traits.get(ReviewTrait)            # None
traits.get_all_traits(OrderTrait)  # every OrderTrait in the container
OrderTrait in traits               # True
```

- **One container per handler.** A handler creates exactly one container for exactly one event.
  An order handler creates an order container, even if the marketplace API reports orders
  through messages.
- `container[T]` returns the first trait that is an instance of `T` (including its subclasses)
  and raises `KeyError` if there is none. A container can hold several traits of the same type
  or with the same base class; `get_all_traits(T)` returns all of them.
- The **shape** of a container is the set of types of its traits. Expressions are resolved by
  the shape, and the result is cached per shape.
- A text without any data is evaluated with an empty container:
  `manager.evaluate(text)` is `manager.evaluate(text, TraitsContainer())`.

### Expressions
```python
@manager.register(call_key='order_id', category=('general', 'order'))
@expression(requires=OrderTrait, docs=ExpressionDocs(...))
async def order_id(traits: TraitsContainer) -> str:
    return traits[OrderTrait].order_id


@manager.register(call_key='order_link', category=('funpay',))
@expression(requires=FunPayOrderTrait, docs=ExpressionDocs(...))
async def order_link(traits: TraitsContainer) -> str: ...
```

- `requires` lists the trait types the expression needs: one type or several. Without
  `requires`, the expression is available everywhere, including texts without data.
  The requirement is part of the definition, so it is the same wherever the expression is
  registered.
- The first positional parameter receives a **view** of the container: a `TraitsView` that holds
  only the traits of the required types. Asking it for any other trait type raises
  `UndeclaredTraitError`, so an expression cannot depend on a trait it did not declare.
  Asking for a base class of a required type is allowed: an expression that requires
  `FunPayOrderTrait` can use `traits[OrderTrait]`.
- All other parameters are filled from the template arguments.
- `category` is a documentation field only (`math`, `string`, `order`, ...). It groups expressions
  in the documentation UI and never affects resolution.
- `renderer` is an optional method that converts the raw result of a top-level call into a string
  or a [fragment](#fragments). Without it, a fragment is kept and any other value is converted with
  `str()`. Results of nested calls are passed to the outer expression as-is.
- **(planned)** An expression ID that is unique within the app, used in error messages, logs and
  documentation. The owner of a definition (a component name or a plugin ID), recorded
  automatically and used in error messages and to isolate plugin errors. Binding one definition
  under several names (aliases).

### Resolution
A container satisfies a requirement if, for every required type, it holds a trait of that type
or of its subclass. For a call `$name`, the candidates are the expressions registered under
`name` whose requirements the container satisfies. **The most specific candidate wins.**

A requirement `A` is more specific than a requirement `B` if every type of `B` is covered by the
same type or a subclass in `A`, and not the other way round. So a requirement with a subclass
wins over one with its base class, and a requirement with more types wins over one with fewer:

- `FunPayOrderTrait` is more specific than `OrderTrait`.
- `(OrderTrait, InitiatorTrait)` is more specific than `OrderTrait` and than `InitiatorTrait`.
- `OrderTrait` and `ReviewTrait` are not comparable.

The order of traits in a container, the order of types in a requirement and the order of
registration never affect the result.

If one candidate is more specific than all the others, it is called. If there is no candidate,
the call raises `UnknownExpressionError`. If several candidates are equally specific (for
example, `$x` is registered for `OrderTrait` and for `ReviewTrait` and the container has both),
the call raises `AmbiguousExpressionError`. Register an override for the traits of all of them
(`(OrderTrait, ReviewTrait)`) to fix it.

Examples:
- `$upper` requires nothing and works everywhere.
- `$order_id` requires `OrderTrait` and works in the order containers of every marketplace,
  including marketplaces and plugins added later.
- `$order_link` requires `FunPayOrderTrait` and does not exist for orders of other marketplaces.

`manager.get_scope(traits)` returns the resolved expressions for a container or for a set of
trait types (`scope.expressions`, `scope.ambiguous`, `scope.expressions_by_category`).

#### Overrides
A more specific expression may replace a less specific one with the same name, but only explicitly:

- An expression that is more specific than another expression with the same name must be
  registered with `override=True`. Without it, `freeze()` fails with an error that names both
  expressions. This prevents a plugin from silently shadowing an existing expression.
- `override=True` on an expression that is not more specific than any other expression with the
  same name is also an error (usually it means the overridden expression was renamed or removed).
- Two expressions with the same name and the same requirement are an error.
- An override must accept every argument that the overridden expression accepts.

```python
@manager.register(call_key='order_id', category=('general', 'order'), override=True)
@expression(requires=FunPayOrderTrait, docs=ExpressionDocs(...))
async def funpay_order_id(traits: TraitsContainer) -> str:
    return f'#{traits[FunPayOrderTrait].order_id}'
```

- **(planned)** An override can call the overridden implementation
  (`*, parent: ParentExpression`).

### Lifecycle
1. **Registration.** During app setup, components and component extensions (plugins) register
   traits, categories and expressions. Registration order does not matter.
2. **Freeze.** After all components and extensions are installed (before the app context
   is locked), `manager.freeze()` checks the registrations:
   - A required trait that is not registered and a wrong use of `override` are errors.
     `freeze()` raises `ExpressionsConfigurationError` with every problem found, and the manager
     stays unfrozen.
   - For every pair of equally specific expressions with the same name, `freeze()` checks that
     there is an expression that covers the traits of both. If there is none, it logs a warning
     and adds it to `manager.warnings`: the combination may be impossible in practice, and
     `AmbiguousExpressionError` at runtime is the backstop.
   - Registration after freeze is an error.
   - **(planned)** Configuration errors caused by a plugin's registration remove that
     registration, are returned to the app by `freeze()` and do not stop the app.
3. **Evaluation** resolves names for the shape of the container on first use and caches the
   result.
4. **(planned) Reconfiguration.** Enabling or disabling a plugin at runtime rebuilds the manager
   state and replaces it atomically. Evaluations that are already running finish with the old one.

### Documentation UI
The Telegram component shows expressions in the "Выражения" menu
(`hubplatform.app.components.telegram.expressions`):

- Registered traits are **filters**. The user selects the traits a text has, and the menu shows
  the expressions available for an imaginary container with traits of these types, with
  overrides resolved. Without selected traits, it shows the expressions that work in any text.
- Categories group the list. Categories without available expressions are hidden.
- The page of an expression shows its documentation and the traits it requires.

### Formatting (planned)
```python
result = await manager.format(text, traits, ignore_errors=app_setting)
result.result    # formatted text
result.errors    # dict[int, ExpressionsFormatError]; always empty with ignore_errors=False

@dataclass(frozen=True)
class ExpressionsFormatResult:
    result: str
    errors: Mapping[int, ExpressionsFormatError]

class ExpressionsFormatError(HubPlatformError):
    span: tuple[int, int]                  # the failed call (may be nested) in the original text
    call: Call | None                      # None for syntax errors
    shape: frozenset[type[Trait]]          # the shape of the container
    owner: str | None                      # owner of the failed expression, if known
    # the original exception, if any, is stored in __cause__

class ExpressionsSyntaxError(ExpressionsFormatError):
    position: int                          # exact position of the syntax error in the original text
```
For a syntax error, `span` is the broken call as determined by the
[recovery rules](#recovering-from-syntax-errors).

1. The whole text is parsed first. Parsed texts are cached by their source text.
2. Calls are evaluated sequentially, in text order.
3. For each top-level call, the name is resolved for the shape of the container. Arguments are
   resolved recursively: nested calls are evaluated and their raw results are passed as arguments.
4. The expression is called. The result of the top-level call is converted with the renderer
   (or `str()`) and replaces the call.

### Fragments
Some results are not text: an image, a file, a break between messages. An expression returns them
as a `Fragment` (`hubplatform.expressions.fragments`):

```python
@dataclass(frozen=True)
class Image(Fragment):
    path: str

    def text_fallback(self) -> str:   # used where only text is possible; '' by default
        return '[image]'
```

`manager.evaluate(text, traits, ignore_errors=...)` returns an `EvaluationResult`:

- `parts` - text and fragments in text order, for example `('Your key: ', Image('key.png'), ' Thanks!')`.
  Neighbouring text is merged into one string and empty strings are dropped.
- `errors` - errors of failed calls (only with `ignore_errors=True`).
- `has_fragments`.
- `text` - the result as text, with fragments replaced by their text fallbacks. Use it where only
  text can be used: `(await manager.evaluate(text, traits)).text`.

Rules:

- A `Fragment` returned by a top-level call is kept as an object. If the expression has a renderer,
  the renderer decides: it must return a string or a `Fragment`.
- A `Fragment` returned by a nested call is passed to the outer expression as-is, like any other value.
- Every top-level call is executed exactly once, even if it has a renderer, so expressions with side
  effects (for example, taking goods from a source) are safe.

The platform does not decide how fragments are sent. That is up to the code that sends the result:
for example, a marketplace that cannot send text and an image in one message splits the parts into
several messages, while Telegram can send an image with the text as its caption.

### Errors (planned)
Every `$` in the text that is not part of `$$` starts an expression call. Every error belongs to
exactly one **top-level** call:

- `ExpressionsSyntaxError` - the call cannot be parsed (including `$ `, `$!` and a trailing `$`).
- `UnknownExpressionError` - the name is not available for the container.
  An expression can stop existing at any time, for example when the plugin that provided it is
  removed while texts that use it are saved in the configuration, so this is a regular error.
- `AmbiguousExpressionError` - several expressions with the name are available for the
  container, and none of them is more specific than all the others.
- `ExpressionArgumentsError` - the arguments cannot be bound to the expression's signature.
- `ExpressionExecutionError` - the expression raised an exception.
- `ExpressionRendererError` - the renderer raised an exception.

All of them are subclasses of `ExpressionsFormatError`. The same error objects are used in both
modes:

- `ignore_errors=True`: `format()` never raises an `ExpressionsFormatError`. The source text of
  every failed top-level call stays in `result` as-is, and the remaining calls are evaluated normally.
  `errors` maps the index of the failed top-level call's `$` in the **original** text to its error.
  A top-level call has at most one error: the first failure inside a call fails the whole call.
  If a nested call fails (`$upper($stars_amount)`), the key is the index of the outer call's `$`, and
  the error's `span` points to the nested call itself.
- `ignore_errors=False`: `format()` raises the first error.
  - Syntax errors are raised before any expression is evaluated, so a text with a syntax error causes
    no side effects.
  - Other errors stop formatting at the failed call, and the calls after it are not evaluated.

All indices and spans refer to the original text, not to `result`: positions in `result` shift
after substitution.

The platform does not log formatting errors or notify anyone. The app decides what to do with
them: for example, not send the message, notify the user and log the traceback. `ignore_errors` is an
app setting; the manager does not read it, and the caller passes it on every call, so changes take
effect immediately.

#### Recovering from syntax errors
To keep a broken call as-is and continue parsing, the parser determines where the broken call ends:

- An error in the name (`$ `, `$!`, a trailing `$`): the broken call is the `$` alone.
  Parsing continues right after it, so `Cost: $!` is kept as `Cost: $!`.
- An error in the argument list: the broken call ends at the `)` that closes its `(`. To find it,
  the parser counts `(` and `)` that are not inside double-quoted strings. Inside a string a backslash
  escapes the next character: `\"` does not end the string, while the `"` in `\\"` does.
  If there is no closing `)`, the broken call extends to the end of the text.
- The source text of a broken call is kept raw: `$$` inside it is not unescaped.

### Template validation (planned)
`manager.validate(text, trait_types)` checks a text without evaluating anything and returns all
problems at once: syntax errors, unknown names, and arguments that cannot be bound
(literal arguments only). Problems use the same error types and positions as `format()`.
It is used when a user edits a text in the UI. Syntax errors block saving. Unknown names are
warnings, and the user can still save the text. Every text property declares the trait types
it is formatted with.

Optionally, after freeze, the app can validate all saved texts to find the ones that use names
that no longer exist (for example, after a plugin was removed).

### Example
A G2G component sends a message when a customer creates a new order.

Expressions:
- No requirement: `$upper`, `$round`, `$random`, `$time`, ...
- `InitiatorTrait`: `$username` (the counterparty), `$user_id`.
- `OrderTrait`: `$order_id`, `$order_name`, `$order_amount`, ...
- `G2GOrderTrait`: `$order_bonuses` and other expressions specific to G2G orders.

The handler creates `TraitsContainer(G2GOrderTrait(...), InitiatorTrait(...))` and calls
`manager.evaluate(text, traits)`. Every expression above is available. `$order_bonuses` works
here, but for a FunPay order it is an unknown name.

A review handler puts the review and the order it is about into one container:
`TraitsContainer(FunPayReviewTrait(...), FunPayOrderTrait(...), InitiatorTrait(...))`, so
`$review_text` and `$order_id` both work.

For FunPay, which reports new orders through system messages, the order handler creates only
an order container. `$username` is therefore the buyer, not the FunPay system account that sent
the message. The new-message handler must not evaluate texts for these system messages.
