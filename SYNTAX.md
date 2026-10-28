# Nacre-11 syntax, version 0.1

The authoritative parser is `src/nacre/language.py`. Source files use UTF-8 and the `.nac` extension. CLI file loading also accepts a UTF-8 BOM. Whitespace separates tokens; `#` starts a comment through the end of its line. Every statement ends with `;`. Newlines have no grammatical significance.

```ebnf
program       = { statement } ;
statement     = use | include | binding | task | verification | emission ;
use           = "use", identifier, "=", string, ";" ;
include       = "include", string, ";" ;
binding       = "let", identifier, ":", type, "=", expression, ";" ;
task          = "task", identifier, ":", type, "<-", capability,
                "(", [ arguments ], ")", [ "retry", integer ], ";" ;
capability    = identifier, { ".", identifier } ;
arguments     = argument, { ",", argument } ;
argument      = identifier, "=", expression ;
verification  = "verify", expression, ";" ;
emission      = "emit", expression, ";" ;
type          = "Any" | "Null" | "Bool" | "Integer" | "Number" | "String"
              | "List" | "Record" | "Table" | "Symbolic" | "Artifact" | "Object" ;

expression    = disjunction ;
disjunction   = conjunction, { "or", conjunction } ;
conjunction   = negation, { "and", negation } ;
negation      = "not", negation | equality ;
equality      = comparison, { ("==" | "!="), comparison } ;
comparison    = sum, { ("<" | "<=" | ">" | ">="), sum } ;
sum           = product, { ("+" | "-"), product } ;
product       = signed, { ("*" | "/" | "%"), signed } ;
signed        = ("+" | "-"), signed | power ;
power         = postfix, [ "^", signed ] ;
postfix       = primary, { ".", identifier | "[", expression, "]" } ;
primary       = number | string | "true" | "false" | "null" | identifier
              | "(", expression, ")"
              | "[", [ expression, { ",", expression } ], "]"
              | "{", [ field, { ",", field } ], "}" ;
field         = (identifier | string), ":", expression ;
identifier    = letter_or_underscore, { letter_or_underscore | digit } ;
integer       = digit, { digit } ;
number        = integer, [ ".", integer ], [ ("e" | "E"), ["+" | "-"], integer ] ;
```

Identifiers use ASCII letters, digits and `_`, beginning with a letter or `_`. Strings use double quotes and JSON escape rules. Numeric signs are operators rather than part of number tokens. Decimal and exponent literals become finite binary floating-point numbers; ordinary whole-number literals become integers. Integer literals are limited to 4,300 decimal digits consistently across supported Python versions. Retry counts must be integer literals in `0..10`; signs, fractions and exponent-form floats are not accepted as retry counts. Duplicate record fields and duplicate named arguments are rejected; trailing commas are not accepted.

Quoted punctuation and keywords are always string values. A string such as `"+"`, `"]"` or `"retry"` never substitutes for a grammar token. For example, `["}", "]"]` is a valid list of strings, while `1 "+" 2` is a syntax error.

`use`, `include`, `let`, `task`, `verify`, `emit`, `retry`, `true`, `false`, `null`, `and`, `or` and `not` cannot be declared as value names or capability aliases. Record keys can still be quoted strings.

The EBNF above describes conventional expressions; the Pratt parser additionally permits prefix operators at an expression start wherever a right operand is parsed. Type checking rejects invalid combinations. The executable precedence table is:

| Binding power | Operators | Association |
|---|---|---|
| 90 | `.field`, `[index]` | left |
| 80 | `^` | right |
| 70 | unary `+`, unary `-` | prefix |
| 60 | `*`, `/`, `%` | left |
| 50 | `+`, `-` | left |
| 40 | `<`, `<=`, `>`, `>=` | left |
| 30 | `==`, `!=` | left |
| 25 | `not` | prefix |
| 20 | `and` | left |
| 10 | `or` | left |

Thus `-2^2` means `-(2^2)`, `2^3^2` means `2^(3^2)`, and `not x == y` means `not (x == y)`. Comparison chaining is ordinary left association, not Python's chained comparison semantics; write `a < b and b < c`.

There are no expression calls. Capability calls appear only in `task` statements with named arguments. There are no user functions, loops, assignment updates, interpolation, SQL statements at top level, macros, exceptions-as-syntax or host-language escape blocks.

`include` resolves relative to the including file, or to the execution workspace for source submitted as text. Included files must be `.nac` files inside that workspace. Includes are expanded once into one flat declaration scope; include cycles and excessive include depth are errors. `use` binds a capability namespace alias; it does not import arbitrary Python modules.
