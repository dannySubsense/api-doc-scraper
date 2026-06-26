# S2 Spike Result — markdownify code_language_callback

| Field | Value |
|---|---|
| Date | 2026-06-25 |
| markdownify version | 1.2.2 |
| Status | CONFIRMED — kwarg approach works (with corrected callback) |

---

## Question

Does `markdownify` 1.2.2 accept `code_language_callback` as a kwarg to `markdownify()`
and emit `` ```lang `` fenced blocks from `class="language-XXX"` elements?

## Result: PASS (kwarg approach — with one correction)

`code_language_callback` **is a recognised option** in markdownify 1.2.2. Passing it as a
kwarg to `markdownify()` is accepted without `TypeError`.

**Critical correction to the spec's `_code_language` implementation:** The callback
receives the `<pre>` element, **not** the `<code>` element. The language class
(`class="language-typescript"`) lives on the child `<code>` element. The spec's draft
callback only inspected `el.get("class")` — this returns `None` for the `<pre>` and
produces an untagged fence. The corrected callback must also inspect `el.find("code")`.

### Minimal working snippet (Slice 3 can lift this verbatim)

```python
import re
from markdownify import markdownify

def _code_language(el) -> str:
    """
    Return the language token for a <pre> element, or '' if none.
    el is always the <pre>; the language class is on the child <code>.
    Matches class="language-<token>" (Prism.js convention).
    """
    classes = list(el.get("class") or [])
    code_child = el.find("code")
    if code_child:
        classes += list(code_child.get("class") or [])
    for cls in classes:
        m = re.match(r"^language-(.+)$", cls)
        if m:
            return m.group(1)
    return ""

def to_markdown(container) -> str:
    _strip_noise(container)
    return markdownify(
        str(container),
        heading_style="ATX",
        code_language_callback=_code_language,
        strip=["script", "style"],
    )
```

### Test output (empirical)

Input HTML:
```html
<pre><code class="language-typescript">const x = 1;</code></pre>
```

Output:
```
```typescript
const x = 1;
```
```

AC-1b check: output starts with `` ```typescript `` — PASS.

---

## Table fidelity

Input:
```html
<table>
  <thead><tr><th>Name</th><th>Value</th></tr></thead>
  <tbody>
    <tr><td>foo</td><td>bar</td></tr>
    <tr><td>baz</td><td>qux</td></tr>
  </tbody>
</table>
```

Output:
```
| Name | Value |
| --- | --- |
| foo | bar |
| baz | qux |
```

VERDICT: PASS — GFM markdown table produced correctly.

---

## Heading hierarchy

Input: `<h1>`, `<h2>`, `<h3>` with `heading_style="ATX"`.

Output:
```
# Top Level

## Second Level

### Third Level
```

VERDICT: PASS — ATX `#`/`##`/`###` hierarchy preserved.

---

## Gotchas

1. **Callback receives `<pre>`, not `<code>`** — the most important correction. The spec's
   draft `_code_language` only checks `el.get("class")` (the `<pre>`). This will always
   return `''` for the standard `<pre><code class="language-x">` pattern. Fix: also
   inspect `el.find("code").get("class")`.

2. **`code_language` default is `''`** — if the callback returns `''` or `None`, markdownify
   falls back to the `code_language` option value (also `''` by default), producing an
   untagged fence. The corrected callback's `return ""` fallback is correct.

3. **`convert_pre` owns the fence; `convert_code` does not** — `convert_code` only handles
   inline code spans (backtick delimited). Fenced blocks are entirely generated in
   `convert_pre`. Do not override `convert_code` to add language tags.

4. **Subclass approach is NOT needed** — the kwarg is a first-class supported option in
   1.2.2. The `MarkdownConverter` defaults block shows `code_language_callback = None`
   as a recognized option alongside `code_language = ''`.

5. **Language token passthrough** — the callback returns the token as-is from the class
   (e.g. `typescript`, `python`, `js`). No mapping needed; Prism.js class names match
   standard fenced-code language identifiers.

---

## Chosen approach for htmlmd.py

**Use the kwarg** (`code_language_callback=_code_language` passed to `markdownify()`).
No subclassing required.

The corrected `_code_language` function above is the implementation Slice 3 must use —
it supersedes the draft version in `02-ARCHITECTURE.md §htmlmd configuration` which only
inspects `el.get("class")` and would silently produce untagged fences.

---

## GO signal for Slice 3

GO. The kwarg approach works in markdownify 1.2.2. Use the corrected snippet above.
Update `htmlmd.py`'s `_code_language` to inspect the child `<code>` element.
