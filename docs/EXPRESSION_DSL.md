# Exact rational expression checker

`rational_expression_upper_bound` checks whether one rational point in a declared
bounded domain makes a restricted rational expression strictly greater than an
explicit rational upper bound. It evaluates one witness; it does not prove a
global inequality or the assumptions of a theorem.

The checker receives structured JSON nodes. It never parses expression text and
never evaluates Python, imports names, calls functions, accesses attributes, or
loads code from a case. Every node has exactly the fields shown below:

| Node | Fields | Meaning |
| --- | --- | --- |
| `const` | `op`, `value` | Exact integer or fraction string |
| `var` | `op`, `name` | A declared domain variable |
| `add` | `op`, `args` | Sum of 2 to 8 expressions |
| `sub` | `op`, `left`, `right` | Exact subtraction |
| `mul` | `op`, `args` | Product of 2 to 8 expressions |
| `div` | `op`, `left`, `right` | Exact division; the evaluated right side must be nonzero |
| `neg` | `op`, `arg` | Exact negation |
| `pow` | `op`, `base`, `exponent` | Integer power from 0 through 12 |

For example, this formalization checks `(x^2 - 1) / (x - 1) <= 2` at `x = 2`:

```json
{
  "kind": "rational_expression_upper_bound",
  "domain": {
    "x": {"lower": "1", "upper": "3", "lower_closed": false, "upper_closed": true}
  },
  "expression": {
    "op": "div",
    "left": {
      "op": "sub",
      "left": {"op": "pow", "base": {"op": "var", "name": "x"}, "exponent": 2},
      "right": {"op": "const", "value": "1"}
    },
    "right": {
      "op": "sub",
      "left": {"op": "var", "name": "x"},
      "right": {"op": "const", "value": "1"}
    }
  },
  "upper_bound": "2"
}
```

The corresponding witness is:

```json
{"kind": "rational_expression_upper_bound", "point": {"x": "2"}}
```

The checker reports the exact value `3` and `REFUTED_FOR_FORMALIZATION`. A
different point or a value at most `2` reports `NO_REFUTATION_AT_WITNESS`.
Inputs outside the grammar, division by zero, an out-of-domain point, or any
resource-limit violation raise `Invalid` and stop evaluation.

The core enforces 1 to 8 domain variables, at most 256 AST node visits, AST
depth at most 20 (root depth zero), powers from 0 to 12, rational inputs using
the existing 64-digit numerator/denominator limits, and at most 8192 bits in
each retained exact numerator and denominator. Powers are checked against a
conservative output-size estimate before calculation. Binary arithmetic combines
only retained values, so even its temporary operands stay below 16,385 bits.
The interchange schema describes the node shapes; the Python core enforces the
evaluation and work limits.

The result covers only the stated formalization and supplied witness. Domain
membership does not prove that the source claim was transcribed correctly, and
one point does not establish a universal inequality.
