# Expressions

## Purpose
Expressions allow embedding evaluated values in string literals.

## Syntax
- Expressions can be embedded in strings using the `$` syntax: `$expression`.
- An expression name may contain only ASCII letters, digits and `_`, and must not start with a digit.
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
  `$expression( a , b )` is the same as `$expression(a,b)`. To include whitespace in a
  string, enclose the string in double quotes: `" a "`.
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
  errors, and so is `$5`, because an expression name cannot start with a digit.
- `$$` is processed first, from left to right:
  - `$$name` is rendered as `$name`;
  - `$$$name` is rendered as `$` followed by the value of the `$name` expression.
- Escaping applies only to the text of a string. Inside quoted string arguments `$` has no
  special meaning and is passed as-is: `$expression("cost: $5")` receives the string `cost: $5`.

### Argument types
Expressions can accept values of any type, including values returned by other expressions.
However, the syntax for passing arguments directly is defined only for the following types:

- **Integers**: written as-is, optionally with a leading `-`, without any other characters or spaces.
  Examples: `123`, `-5`.
- **Floats**: written as-is, optionally with a leading `-`.
  Must include both an integer part and a fractional part, separated by a decimal point (`.`), with no spaces.
  Examples: `123.321`, `-0.5`.
- **Booleans**: `true` or `false`, case-sensitive.
- **Null**: `null`, case-sensitive (as in JSON).
- **Strings**: can be written without quotes if they contain no characters from the set
  `[](){}:=,$\"` and no whitespace. Otherwise, they must be enclosed in double quotes (`"`).
  If an unquoted value matches the syntax of another supported type, it is interpreted as that type.
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

> Code examples below are pseudocode. Error handling and the API
> (creating expressions, catalogs, scopes, groups) are described separately.

### Entities
The expressions system consists of the following parts:

1. `ExpressionObject` - an object that contains an expression function, its requirements
   (the `Capability` types the caller must provide) and documentation
   (a separate structure describing what the expression does).
2. `ExpressionsCatalog` - an object that contains all available `ExpressionObject`s,
   each identified by a unique ID (any string).
3. `ExpressionsScope` - a mapping of expression names (the names used after `$` in text)
   to `ExpressionObject` IDs from an `ExpressionsCatalog`. A scope does not hold any
   `ExpressionObject`s itself; in general it is just a `dict[str, str]`.
   Scopes can be attached to other scopes, forming one-way scope trees:
   a scope knows its subscopes, but a subscope does not know its parent.
4. `Group` - a list of scopes.
5. `Capability` - an object generated by the calling side that carries the context data
   expressions need to work.
6. `ExpressionsManager` - an orchestrator that manages all entities listed above.

### Capabilities
Each `ExpressionObject` declares its requirements: the `Capability` types it depends on.
For an expression to work correctly, the caller must pass all capabilities from the
expression's requirements. Capabilities are matched to requirements by their type.
Capability classes are not required to be related by inheritance.

Capabilities are layered by generality:

- **General capabilities** have the same structure for every marketplace. Expressions
  that depend only on them work "out of the box" in any component, as long as the caller
  of that component generates them. When a component for a new marketplace is added,
  its caller only has to generate the general capabilities.
- `GeneralActionCapability` is needed so that some expressions work in every context.
  For example, `$username` depends on it and is rendered as the message sender in a
  new-message context and as the buyer in a new-order context. There is a single
  implementation of `$username`; the caller is responsible for filling
  `GeneralActionCapability` correctly.
- **Marketplace-specific capabilities** are used by marketplace-specific expressions,
  which can be added later without affecting the general ones.

### Call mechanism
First, the caller must generate `Capability` objects to pass to expressions.

Let's assume we are writing a function for the G2G marketplace that sends a text message
when a customer creates a new order. This function lives in an app that consists of several
components, one for each marketplace (e.g., G2G, FunPay, Playerok).

We have the following scopes:
1. Global scope: expressions that work without any context (e.g., `$upper`, `$round`, `$random`).
2. General scope:
   1. General order-related scope
   2. General message-related scope
   3. General review-related scope
3. G2G scope:
   1. Order-related scope
   2. Message-related scope
   3. Review-related scope
4. FunPay scope:
   1. Order-related scope
   2. Message-related scope
   3. Review-related scope

The function creates the following capability objects:

- `GeneralActionCapability` - a capability with the same structure for every marketplace
  and event type; the marketplace and the action type are passed as data.
```python
  class GeneralActionCapability:
      actor_username: str
      actor_id: int
      action_type: str
      marketplace_id: str
```
- `GeneralNewOrderCapability` - a "new order" capability with the same structure for every marketplace.
```python
  class GeneralNewOrderCapability:
      order_id: str
      buyer_id: int
      buyer_username: str
      order_name: str | None
      order_description: str | None
      marketplace_id: str
```
- `G2GNewOrderCapability` - a marketplace-specific capability.
```python
  class G2GNewOrderCapability:
      order_id: int
      buyer_id: int
      buyer_username: str
      order_name: str
      order_description: str
      order_sum: G2GSumType
      delivered_by_marketplace_goods: tuple[str, ...]
```

The function then calls `ExpressionsManager` and passes it:
- the string with embedded expression calls to format;
- the generated capability objects;
- a `group_id`, e.g., `G2G_NEW_ORDER_GROUP`.

`G2G_NEW_ORDER_GROUP` consists of the following scopes:
1. General scope → General order-related scope.
2. G2G scope → Order-related scope.

`ExpressionsManager` renders the string as follows:
1. The parser extracts all expression calls from the string.
2. For each call, the manager looks up the name in the scopes of the passed group.
3. If the name is not found there, the manager looks it up in the global scope.
4. If the name is found, the expression is evaluated with the capabilities from its
   requirements, and its result replaces the call.
5. If the name is not found anywhere, the call is skipped and left in the string as-is.