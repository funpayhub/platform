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
  - A keyword argument name must be a valid Python parameter name.
  - A keyword argument value can be of any supported type, including another expression call.
  - Positional arguments must come before keyword arguments, and a keyword name
    must not be repeated.
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
- **Floats**: an optional leading `-`, an integer part without leading zeros, a decimal point (`.`)
  and a non-empty fractional part (regex: `-?(0|[1-9][0-9]*)\.[0-9]+`).
  Examples: `123.321`, `-0.5`, `10.0`.
- Any other numeric-looking value is a string, not a number: for example `007`, `1.`, `.5`,
  `+1`, `1e5`, `NaN`, `Infinity` and `-Infinity` are all strings.
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
  Keys can be a value of any non-container supported type.
  Duplicate keys are not allowed and cause a parsing error.
  Keys are compared the same way as Python `dict` keys: values that are equal in Python are the
  same key. In particular, `1`, `1.0` and `true` are equal, as are `0`, `0.0` and `false`.
  So `{1: a, true: b}` and `{0: a, 0.0: b}` are duplicate-key errors, while `{1: a, "1": b}` is valid,
  because the string `"1"` is not equal to the integer `1`.
  Values can be of any supported type, including nested sequences, mappings and other expression calls.
  Example: `{some_key: 123, 1000: {another: mapping}, "some call": $other_expression(123, arg2)}`

## Implementation

> Code examples below are pseudocode. They show the shape of the API, not final names or signatures.

### Overview
Expressions are resolved like Python methods. Each handler renders a text with exactly one
**context object**. The set of available expressions, and the implementation that each name
refers to, is determined by the context's class and its ancestors: the nearest definition wins.

The system consists of the following parts:

1. `ExpressionsContext` - the root class of all contexts. A context object carries the data
   that expressions need. Context classes form a single-inheritance tree.
2. `ExpressionDefinition` - an expression function together with its metadata: a unique ID,
   documentation, a category, an optional renderer and its owner.
3. `ExpressionsScope` - the set of name bindings for one context type. There is exactly one scope
   per context class. Scopes are not created or nested manually: the scope tree is the context
   class tree.
4. `ExpressionsManager` - an orchestrator that owns all scopes, validates them, compiles them
   into an immutable snapshot and renders texts.

### Contexts
```python
class ExpressionsContext: ...                          # root; used by texts without any context

@dataclass(kw_only=True)
class GenericOrderContext(ExpressionsContext):        # concrete, can be used directly by handlers
    order_id: str                                      # normalized, cross-marketplace form
    counterparty_username: str
    order_sum: Decimal | None = None                   # data that not every marketplace provides

@dataclass(kw_only=True)
class FunPayOrderContext(GenericOrderContext):
    order: funpay.Order                                # native object with native types

    @classmethod
    def from_order(cls, order: funpay.Order) -> FunPayOrderContext:
        return cls(
            order=order,
            order_id=str(order.id),                    # funpay.Order.id is an int
            counterparty_username=order.buyer.username,
        )
```

Rules:

- **One context per handler.** A handler creates exactly one context object, for exactly one
  logical context. An order handler creates an order context and nothing else, even if the
  marketplace API reports orders through messages.
- **Single inheritance.** A context class has at most one base class that is a subclass of
  `ExpressionsContext`; this is checked in `ExpressionsContext.__init_subclass__`, at class
  definition. Mixins that are not contexts are allowed.
- **Generic contexts are concrete.** A generic context (`GenericOrderContext`,
  `GenericMessageContext`, `GenericReviewContext`, ...) is a plain data class with normalized
  fields that every marketplace can provide. A handler can create it directly: a new component
  can start with `GenericOrderContext` and introduce a specific context later. All generic
  expressions (`$username`, `$order_id`, ...) are implemented in the generic scope, and more
  specific scopes may override them.
- **Field types are never changed in child contexts.** Required generic fields are filled by the
  child context's constructor in their normalized form (`order_id=str(order.id)`). Data that not
  every marketplace provides is optional (`None` by default). Marketplace-specific data with
  native types is stored separately, usually as the native object itself
  (`FunPayOrderContext.order`), and is used by marketplace-specific expressions.
- **Expensive data.** Data that has to be fetched is exposed as an `async` method with a default
  implementation in the generic context (for example, returning `None`). Specific contexts
  override it and cache the result.
- **The context tree is open.** "Root → generic logical contexts → marketplace contexts" is a
  convention, not a fixed structure:
  - A marketplace can introduce a completely new logical context by subclassing
    `ExpressionsContext` directly (for example `G2GDisputeContext(ExpressionsContext)`).
    It gets the root expressions and its own ones.
  - When a second marketplace gets the same concept, a generic context is extracted
    (`GenericDisputeContext(ExpressionsContext)`), and both marketplace contexts are reparented to
    it. Common expressions move to the generic scope under the same names, so saved texts keep
    working. A marketplace binding that now shadows a generic one without `override=True` is
    reported at freeze, so every collision is reviewed during the migration.
  - The tree can be deeper where it's useful
    (`FunPayOrderContext → FunPayStarsOrderContext`).
  - To avoid two parallel generic hierarchies for the same concept, generic contexts are defined
    in one place: `hubplatform` or one shared package. Marketplace components and plugins only
    extend them.
- **Composition instead of multiple inheritance.** If one context is also about another logical
  entity (a review is about an order), it holds that entity as an attribute
  (`GenericReviewContext.order: GenericOrderContext`) and can re-export its expressions
  (see [Re-exporting expressions](#re-exporting-expressions)).

### Expressions
```python
@manager.scope(GenericOrderContext).expression(
    'order_id',
    id='hubplatform:order_id',
    category='order',                      # documentation only
    docs=Docs('expr-order_id'),            # i18n keys, not literal text
)
async def order_id(ctx: GenericOrderContext) -> str:
    return ctx.order_id
```

- The first positional parameter is the context object. Its type is the scope's context type
  (or a superclass of it), so the expression is type-safe.
- All other parameters are filled from the template arguments. Arguments are bound with
  `inspect.Signature.bind`; binding errors are expression errors.
- There is no dependency injection by name. Components and plugins register expressions during
  their setup and capture the services they need (bound methods, closures, instances).
- An expression ID is unique within the app. IDs are used in error messages, logs and documentation,
  and to refer to an expression from code. They never appear in templates.
- `category` is a documentation field only (`math`, `string`, `order`, ...). It groups expressions
  in the documentation UI and never affects resolution.
- `renderer` is an optional function that converts the raw result of a top-level call into a string.
  Without it, `str()` is used. Results of nested calls are passed to the outer expression as-is.
- The owner of a definition (a component name or a plugin ID) is recorded automatically and used in
  error messages and to isolate plugin errors.
- The same definition can be bound under several names (aliases).

### Scopes and resolution
`manager.scope(T)` returns the scope of context type `T`, creating it if needed.
Its parent scope is the scope of `T`'s base context class.

Rendering with a context object `ctx` uses the scopes of all classes in `type(ctx).__mro__`
that are subclasses of `ExpressionsContext`, from the most specific to `ExpressionsContext`.
For each name, **the nearest binding wins**.

Examples:
- `$upper` is bound in the scope of `ExpressionsContext` and works everywhere.
- `$order_id` is bound in the scope of `GenericOrderContext` and works in every marketplace's
  order context, including marketplaces and plugins added later.
- `$order_sum` can be bound in the scope of `FunPayOrderContext` only; it does not exist in
  other contexts.

#### Overrides
A child scope may replace an expression of an ancestor scope, but only explicitly:

- Binding a name that is already bound in an ancestor scope requires `override=True`.
  Without it, the binding is a configuration error that names both owners. This prevents a plugin
  from silently shadowing an existing expression.
- `override=True` on a name that no ancestor binds is also an error
  (usually it means the overridden expression was renamed or removed).
- Two bindings of the same name in the same scope are an error.
- An override must accept every argument that the overridden expression accepts.
- An override can call the overridden implementation:

```python
@manager.scope(G2GOrderContext).expression('username', id='g2g:username', override=True)
async def g2g_username(ctx: G2GOrderContext, *, parent: ParentExpression) -> str:
    return f'@{await parent(ctx)}'
```

#### Re-exporting expressions
A scope can make expressions of a composed context available under its own names:

```python
manager.scope(GenericReviewContext).reexport(
    GenericOrderContext, via=lambda ctx: ctx.order, names=['order_id', 'order'],
)
```

At render time a re-exported name is resolved against `type(via(ctx))`, so
in a FunPay review context, `$order_id` uses the FunPay order context and its overrides.
Re-exported names follow the same collision and override rules as other bindings.

### Lifecycle
1. **Registration.** During app setup, components and component extensions (plugins)
   create contexts, register expressions, aliases and re-exports. Registration order
   does not matter.
2. **Freeze.** After all components and extensions are installed (before the app context
   is locked), `manager.freeze()` validates every scope and compiles an immutable snapshot:
   for every known context type, a `dict[name, binding]` with all resolution already done.
   - Configuration errors from core code and components fail the app setup.
   - Configuration errors caused by a plugin's binding remove that binding, are returned
     to the app by `freeze()` and do not stop the app.
   - Registration after freeze is an error.
3. **Formatting** uses the current snapshot. A context type that was not seen at freeze time
   (a subclass defined later) is resolved on first use with the same rules and cached.
4. **Reconfiguration.** In the future, enabling or disabling a plugin at runtime recompiles the
   snapshot and replaces it atomically. Formatting calls that are already running finish with the
   old one.

### Formatting
```python
result = await manager.format(text, ctx, ignore_errors=app_setting)
result.result    # formatted text
result.errors    # dict[int, ExpressionsFormatError]; always empty with ignore_errors=False

@dataclass(frozen=True)
class ExpressionsFormatResult:
    result: str
    errors: Mapping[int, ExpressionsFormatError]

class ExpressionsFormatError(HubPlatformError):
    span: tuple[int, int]                  # the failed call (may be nested) in the original text
    call: Call | None                      # None for syntax errors
    context_type: type[ExpressionsContext]
    owner: str | None                      # owner of the failed expression, if known
    # the original exception, if any, is stored in __cause__

class ExpressionsSyntaxError(ExpressionsFormatError):
    position: int                          # exact position of the syntax error in the original text
```
For a syntax error, `span` is the broken call as determined by the
[recovery rules](#recovering-from-syntax-errors).

1. The whole text is parsed first. Parsed texts are cached by their source text.
2. Calls are evaluated sequentially, in text order.
3. For each top-level call, the name is resolved in the snapshot for `type(ctx)`. Arguments are
   resolved recursively: nested calls are evaluated and their raw results are passed as arguments.
4. The expression is called. The result of the top-level call is converted with the renderer
   (or `str()`) and replaces the call.

#### Errors
Every `$` in the text that is not part of `$$` starts an expression call. Every error belongs to
exactly one **top-level** call:

- `ExpressionsSyntaxError` - the call cannot be parsed (including `$ `, `$!` and a trailing `$`).
- `UnknownExpressionError` - the name does not exist in the context.
  An expression can stop existing at any time, for example when the plugin that provided it is
  removed while texts that use it are saved in the configuration, so this is a regular error.
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

### Template validation
`manager.validate(text, context_type)` checks a text without evaluating anything and returns all
problems at once: syntax errors, unknown names, and arguments that cannot be bound
(literal arguments only). Problems use the same error types and positions as `format()`.
It is used when a user edits a text in the UI. Syntax errors block saving. Unknown names are
warnings, and the user can still save the text. Every text property declares the context type
it is formatted with.

Optionally, after freeze, the app can validate all saved texts to find the ones that use names
that no longer exist (for example, after a plugin was removed).

### Example
A G2G component sends a message when a customer creates a new order.

Scopes:
- `ExpressionsContext`: `$upper`, `$round`, `$random`, `$time`, ...
- `GenericOrderContext`: `$username` (the counterparty), `$order_id`, `$order_sum`, ...
- `G2GOrderContext`: `$order_bonuses` and other G2G-specific expressions.

The handler creates `G2GOrderContext(...)` and calls `manager.format(text, ctx, ...)`.
Every expression of the three scopes above is available. `$order_bonuses` works here, but
in a FunPay order context it is an unknown name.

For FunPay, which reports new orders through system messages, the order handler creates only
`FunPayOrderContext`. `$username` is therefore the buyer, not the FunPay system account that sent the
message. The new-message handler must not format texts for these system messages.
