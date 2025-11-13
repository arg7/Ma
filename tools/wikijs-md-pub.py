#!/usr/bin/env python3
r"""
latex_math_transform.py — Markdown math normalizer + self-tests.

Usage:
    python latex_math_transform.py input.md output.md
    python latex_math_transform.py --test
"""
import re
import sys
import unittest
from pathlib import Path


def _normalize_math_content(s: str) -> str:
    r"""
    Normalize spacing and escaped punctuation inside a math block.
    - Preserves leading/trailing newlines for display math.
    - Escaped punctuation (\;, \:, \,, \!) is removed/replaced,
      but ONLY if it's not at the end of a line.
    - Redundant whitespace is collapsed.
    """
    starts_with_newline = s.startswith('\n')
    ends_with_newline = s.endswith('\n')

    s = re.sub(r'\\([;:])(?!\s*\n|\s*$)', ' ', s)
    s = re.sub(r'\\([,!])(?!\s*\n|\s*$)', '', s)
    s = re.sub(r"[ \t]+", " ", s)
    s = s.strip()

    if starts_with_newline:
        s = '\n' + s
    if ends_with_newline:
        s = s + '\n'

    return s


def transform_markdown_math(md_text: str) -> str:
    r"""
    Transform Markdown math per rules:

    Escaped LaTeX:
      - Display: \[ ... \] → $$ ... $$
      - Inline:  \( ... \) → $ ... $

    Relaxed blocks (strip only , ; INSIDE math):
      - [ ... ] (on its own line) → $$ ... $$ and remove commas ; semicolons inside

    Relaxed inline parentheses (outside of existing math):
      - (( ... )) → $( ... )$ if content looks like math
      - ( ... )   → $ ... $   (outermost span only) if content looks like math
    """
    text = md_text

    # ---- 1) Capture relaxed [ ... ] blocks to placeholders
    relaxed_blocks = []

    def _cap_relaxed(m):
        relaxed_blocks.append(m.group(1))
        return f"\n__MABLOCK_{len(relaxed_blocks)-1}__\n"

    text = re.sub(r"\n\[\s*\n(.*?)\n\]\s*\n", _cap_relaxed, text, flags=re.DOTALL)
    text = re.sub(r"\n\[\s*(.*?)\s*\]\s*\n", _cap_relaxed, text, flags=re.DOTALL)

    # ---- 2) Convert escaped LaTeX delimiters, normalizing content
    text = re.sub(r"\\\[(.*?)\\\]", lambda m: f"\n$${_normalize_math_content(m.group(1))}$$\n", text, flags=re.DOTALL)
    text = re.sub(r"\\\(\s*(.*?)\s*\\\)", lambda m: f"${_normalize_math_content(m.group(1))}$", text, flags=re.DOTALL)

    # ---- 3) Mask existing math ($$…$$ and $…$)
    display_math, inline_math = [], []

    def _mask_display(m):
        display_math.append(m.group(0))
        return f"__MADISP_{len(display_math)-1}__"

    def _mask_inline(m):
        inline_math.append(m.group(0))
        return f"__MAINL_{len(inline_math)-1}__"

    text = re.sub(r"\$\$(.+?)\$\$", _mask_display, text, flags=re.DOTALL)
    text = re.sub(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", _mask_inline, text, flags=re.DOTALL)

    # ---- 4) Relaxed inline parentheses conversions
    def looks_like_math(s: str) -> bool:
        return bool(re.search(r"[\\^_=\-+*/<>]|[∂ΩωκθλμνξπστυφχψΓΔΛΞΠΣΦΨΩ]", s))

    def _double_paren(m):
        inner = m.group(1).strip()
        if looks_like_math(inner):
            inner = _normalize_math_content(inner)
            return f"$({inner})$"
        return m.group(0)

    text = re.sub(r"\(\(\s*(.*?)\s*\)\)", _double_paren, text, flags=re.DOTALL)

    paren_outer = re.compile(r"(?<!\\)(?<!\$)\((?:[^()]*|\([^()]*\))*\)", re.DOTALL)

    def _outer_single_paren(m):
        segment = m.group(0)
        inner = segment[1:-1].strip()
        if inner.startswith('$') and inner.endswith('$'):
            return segment
        if looks_like_math(inner):
            inner = _normalize_math_content(inner)
            new_inline = f"${inner}$"
            idx = len(inline_math)
            inline_math.append(new_inline)
            return f"__MAINL_{idx}__"
        return segment

    text = paren_outer.sub(_outer_single_paren, text)

    # ---- 5) Unmask inline math
    def _unmask_inline(m):
        idx = int(m.group(1))
        return inline_math[idx]

    text = re.sub(r"__MAINL_(\d+)__", _unmask_inline, text)

    # ---- 6) Unmask display math
    def _unmask_display(m):
        idx = int(m.group(1))
        return display_math[idx]

    text = re.sub(r"__MADISP_(\d+)__", _unmask_display, text)

    # ---- 7) Reinsert relaxed blocks
    def _reins_relaxed(m):
        idx = int(m.group(1))
        body = relaxed_blocks[idx]
        body = body.replace(",", "").replace(";", "")
        body = _normalize_math_content(body)
        return f"\n$${body}$$\n"

    text = re.sub(r"\n__MABLOCK_(\d+)__\n", _reins_relaxed, text)

    # ---- 8) Final cleanup: Ensure any $$ display block is preceded by a newline.
    # FIX: Use a more robust regex that doesn't add a newline before a closing '$$'.
    text = re.sub(r'([^\n])(\$\$.+?\$\$)', r'\1\n\2', text, flags=re.DOTALL)

    return text


# =========================== CLI ===========================
def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "--test":
        unittest.main(argv=[sys.argv[0]])
        return
    if len(argv) < 2:
        print("Usage: python latex_math_transform.py <input.md> <output.md>")
        sys.exit(1)
    inp = Path(argv[0])
    out = Path(argv[1])
    md = inp.read_text(encoding="utf-8")
    out.write_text(transform_markdown_math(md), encoding="utf-8")
    print(f"Transformed '{inp}' → '{out}'")


# =========================== UNIT TESTS ===========================
class TestLatexMathTransform(unittest.TestCase):
    def test_inline_paren_to_dollar(self):
        src = r"Inline: \( \kappa_m, \xi; \) end."
        out = transform_markdown_math(src)
        m = re.search(r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)", out, re.DOTALL)
        self.assertIsNotNone(m)
        self.assertIn(r"\kappa_m, \xi;", m.group(1))

    def test_relaxed_block_strips_punct(self):
        src = """
Before

[
A, B; C
]

After
"""
        out = transform_markdown_math(src)
        self.assertIn("$$", out)
        # Use findall to safely extract content from $$ blocks
        blocks = re.findall(r"\$\$(.*?)\$\$", out, flags=re.DOTALL)
        self.assertTrue(any(b.strip() == "A B C" for b in blocks))

    def test_double_paren_to_inline_math(self):
        src = r"See (( θ , \xi; )) here."
        out = transform_markdown_math(src)
        self.assertIn("$(", out)
        m = re.search(r"\$\((.*?)\)\$", out)
        self.assertIsNotNone(m)
        inner = m.group(1)
        self.assertIn("θ", inner)
        self.assertIn(",", inner)
        self.assertIn(";", inner)

    def test_single_paren_outermost(self):
        src = r"Example: ( θ, a(b+c); ) and normal (text)."
        out = transform_markdown_math(src)
        self.assertRegex(out, r"\$θ, a\(b\+c\);\$")
        self.assertIn("(text)", out)

    def test_middle_punctuation_removed(self):
        src = r"(ψ \;=\; -\,\frac{∂κ_m}{∂t})"
        out = transform_markdown_math(src)
        self.assertIn(r"$ψ = -\frac{∂κ_m}{∂t}$", out)

    def test_end_punctuation(self):
        src = r"""\[
ξ(κ_m) = ξ_0\,f(κ_m),
\qquad
\frac{dξ}{dκ_m} < 0.
\]"""
        exp = r"""
$$
ξ(κ_m) = ξ_0f(κ_m),
\qquad
\frac{dξ}{dκ_m} < 0.
$$
"""
        out = transform_markdown_math(src)
        self.assertEqual(exp.strip(), out.strip())

    def test_escaped_punctuation_at_eol_is_kept(self):
        src = r"\[ a\, b\; \n c, d; \]"
        out = transform_markdown_math(src)
        # FIX: Use strip() to ignore surrounding newlines added by the script.
        self.assertEqual(r"$$a b \n c, d;$$", out.strip())

    def test_newline_before_display_math(self):
        src = r"Some text before.\[ a = b \]"
        out = transform_markdown_math(src)
        # FIX: Test the stripped output for predictability.
        self.assertEqual("Some text before.\n$$a = b$$", out.strip())

        src2 = "Another test.$$c = d$$"
        out2 = transform_markdown_math(src2)
        self.assertEqual("Another test.\n$$c = d$$", out2.strip())

        src3 = "Already good\n$$ e = f $$"
        out3 = transform_markdown_math(src3)
        self.assertEqual("Already good\n$$ e = f $$", out3.strip())

    def test_mixed_cases(self):
        src = r"""
\[
x, y; \qquad z
\]

(( θ , \xi; ))

( θ , \xi; ) text

[
block, has; punctuation
]

$ inline, keep; this $

Normal (text, not math).
"""
        out = transform_markdown_math(src)
        blocks = re.findall(r"\$\$(.*?)\$\$", out, re.DOTALL)
        self.assertTrue(any("," in b or ";" in b for b in blocks))
        self.assertTrue(any("," not in b and ";" not in b for b in blocks))
        self.assertIn(r"$θ , \xi;$", out)
        self.assertIn("$ inline, keep; this $", out)


if __name__ == "__main__":
    main()