"""Safe spreadsheet formula engine (explicit subset, no eval, no I/O).

Supported syntax
----------------
* Numbers (``.`` decimal), strings ``"texto"`` (``""`` escapes a quote), TRUE/FALSE
  (VERDADERO/FALSO).
* References ``A1``, ``$A$1``, ranges ``A1:B10``, other sheets ``Hoja2!A1`` and
  ``'Hoja con espacios'!A1:B2``.
* Operators: ``+ - * / ^ &`` comparisons ``= <> < > <= >=``, unary ``-``/``+``, postfix ``%``.
* Argument separators: ``,`` or ``;``.

Functions (Spanish/English names): see ``FUNCTION_NAMES``.
Errors: ``#DIV/0!``, ``#REF!``, ``#NAME?``, ``#VALUE!``, ``#N/A``, ``#CIRC!``, ``#NUM!``.
"""
import math
import re
from decimal import Decimal

MAX_ROWS = 1_048_576
MAX_COLS = 16_384


class XLError(Exception):
    """Error value. Also raised internally to short-circuit evaluation."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code

    def __eq__(self, other):
        return isinstance(other, XLError) and other.code == self.code

    def __hash__(self):
        return hash(self.code)

    def __repr__(self):
        return self.code

    def __str__(self):
        return self.code


DIV0, REF, NAME, VALUE, NA, CIRC, NUM = (XLError(c) for c in ("#DIV/0!", "#REF!", "#NAME?", "#VALUE!", "#N/A", "#CIRC!", "#NUM!"))
ERROR_CODES = {e.code: e for e in (DIV0, REF, NAME, VALUE, NA, CIRC, NUM)}


# ------------------------------------------------------------------ references
def col_to_index(col):
    n = 0
    for ch in col.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def index_to_col(idx):
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


CELL_RE = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)(\d{1,7})$")


def parse_cell(ref):
    m = CELL_RE.match(ref)
    if not m:
        raise ValueError(ref)
    return int(m.group(4)) - 1, col_to_index(m.group(2))


def cell_name(row, col):
    return f"{index_to_col(col)}{row + 1}"


# ------------------------------------------------------------------ tokenizer
TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<string>"(?:[^"]|"")*")
  | (?P<error>\#(?:DIV/0!|REF!|NAME\?|VALUE!|N/A|NUM!|CIRC!))
  | (?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_À-ſ][\w.À-ſ]*)!)?\$?[A-Za-z]{1,3}\$?\d{1,7}(?::\$?[A-Za-z]{1,3}\$?\d{1,7})?(?![\w(]))
  | (?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\.\d+)
  | (?P<func>[A-Za-z_À-ſ][\w.À-ſ]*(?=\s*\())
  | (?P<name>[A-Za-z_À-ſ][\w.À-ſ]*)
  | (?P<op><>|<=|>=|[-+*/^&=<>%])
  | (?P<lparen>\()
  | (?P<rparen>\))
  | (?P<sep>[,;])
    """,
    re.VERBOSE,
)


class Token:
    __slots__ = ("kind", "value", "start", "end")

    def __init__(self, kind, value, start, end):
        self.kind, self.value, self.start, self.end = kind, value, start, end

    def __repr__(self):
        return f"{self.kind}:{self.value}"


def tokenize(text):
    pos = 0
    tokens = []
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise FormulaSyntaxError(f"Carácter inesperado «{text[pos]}» en la posición {pos + 1}.")
        kind = m.lastgroup
        if kind != "ws":
            tokens.append(Token(kind, m.group(kind), m.start(), m.end()))
        pos = m.end()
    return tokens


class FormulaSyntaxError(Exception):
    pass


# ------------------------------------------------------------------ AST
class Ref:
    __slots__ = ("sheet", "r1", "c1", "r2", "c2")

    def __init__(self, sheet, r1, c1, r2=None, c2=None):
        self.sheet, self.r1, self.c1 = sheet, r1, c1
        self.r2 = r1 if r2 is None else r2
        self.c2 = c1 if c2 is None else c2
        if self.r2 < self.r1:
            self.r1, self.r2 = self.r2, self.r1
        if self.c2 < self.c1:
            self.c1, self.c2 = self.c2, self.c1

    @property
    def is_range(self):
        return self.r1 != self.r2 or self.c1 != self.c2


def split_sheet(refstr):
    if "!" in refstr:
        sheet, addr = refstr.rsplit("!", 1)
        if sheet.startswith("'"):
            sheet = sheet[1:-1].replace("''", "'")
        return sheet, addr
    return None, refstr


def parse_ref_token(text):
    sheet, addr = split_sheet(text)
    parts = addr.split(":")
    r1, c1 = parse_cell(parts[0])
    if len(parts) == 2:
        r2, c2 = parse_cell(parts[1])
        return Ref(sheet, r1, c1, r2, c2)
    return Ref(sheet, r1, c1)


class Parser:
    PREC = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1, "&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5}

    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        if not self.tokens:
            raise FormulaSyntaxError("Fórmula vacía.")
        node = self.expr(0)
        if self.peek() is not None:
            raise FormulaSyntaxError(f"Símbolo inesperado «{self.peek().value}».")
        return node

    def expr(self, min_prec):
        left = self.unary()
        while True:
            tok = self.peek()
            if tok is None or tok.kind != "op" or tok.value == "%":
                break
            prec = self.PREC.get(tok.value)
            if prec is None or prec < min_prec:
                break
            self.take()
            right = self.expr(prec + 1)  # all binary operators are left-associative (as in Excel)
            left = ("bin", tok.value, left, right)
        return left

    def unary(self):
        tok = self.peek()
        if tok is not None and tok.kind == "op" and tok.value in "+-":
            self.take()
            operand = self.unary()
            return ("neg", operand) if tok.value == "-" else ("pos", operand)
        return self.postfix(self.primary())

    def postfix(self, node):
        while True:
            tok = self.peek()
            if tok is not None and tok.kind == "op" and tok.value == "%":
                self.take()
                node = ("pct", node)
            else:
                return node

    def primary(self):
        tok = self.take()
        if tok is None:
            raise FormulaSyntaxError("La fórmula termina de forma inesperada.")
        if tok.kind == "number":
            return ("num", float(tok.value))
        if tok.kind == "string":
            return ("str", tok.value[1:-1].replace('""', '"'))
        if tok.kind == "error":
            return ("err", ERROR_CODES.get(tok.value, VALUE))
        if tok.kind == "ref":
            try:
                return ("ref", parse_ref_token(tok.value))
            except ValueError:
                return ("err", REF)
        if tok.kind == "name":
            up = tok.value.upper()
            if up in ("TRUE", "VERDADERO"):
                return ("bool", True)
            if up in ("FALSE", "FALSO"):
                return ("bool", False)
            return ("name", tok.value)
        if tok.kind == "func":
            name = tok.value.upper()
            self.take()  # (
            args = []
            if self.peek() is not None and self.peek().kind == "rparen":
                self.take()
                return ("call", name, args)
            while True:
                if self.peek() is not None and self.peek().kind in ("sep", "rparen"):
                    args.append(("empty",))
                else:
                    args.append(self.expr(0))
                tok2 = self.take()
                if tok2 is None:
                    raise FormulaSyntaxError(f"Falta «)» en {name}.")
                if tok2.kind == "rparen":
                    break
                if tok2.kind != "sep":
                    raise FormulaSyntaxError(f"Se esperaba «,» o «)» en {name}.")
            return ("call", name, args)
        if tok.kind == "lparen":
            node = self.expr(0)
            close = self.take()
            if close is None or close.kind != "rparen":
                raise FormulaSyntaxError("Falta cerrar un paréntesis.")
            return node
        raise FormulaSyntaxError(f"Símbolo inesperado «{tok.value}».")


def parse_formula(text):
    """Parse text after the leading '='."""
    return Parser(tokenize(text)).parse()


# ------------------------------------------------------------------ helpers
def is_number(v):
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def to_number(v):
    if isinstance(v, XLError):
        raise v
    if v is None or v == "":
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if is_number(v):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        try:
            if s.endswith("%"):
                return float(s[:-1]) / 100
            return float(s)
        except ValueError:
            raise VALUE
    raise VALUE


def to_text(v):
    if isinstance(v, XLError):
        raise v
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if is_number(v):
        f = float(v)
        if f.is_integer() and abs(f) < 1e15:
            return str(int(f))
        return repr(f)
    return str(v)


def to_bool(v):
    if isinstance(v, XLError):
        raise v
    if isinstance(v, bool):
        return v
    if v is None or v == "":
        return False
    if is_number(v):
        return float(v) != 0
    if isinstance(v, str):
        up = v.strip().upper()
        if up in ("TRUE", "VERDADERO"):
            return True
        if up in ("FALSE", "FALSO"):
            return False
    raise VALUE


def _type_rank(v):
    if is_number(v) or v is None:
        return 0
    if isinstance(v, str):
        return 1
    return 2


def compare(a, b, op):
    if isinstance(a, XLError):
        raise a
    if isinstance(b, XLError):
        raise b
    if a is None:
        a = "" if isinstance(b, str) else (False if isinstance(b, bool) else 0.0)
    if b is None:
        b = "" if isinstance(a, str) else (False if isinstance(a, bool) else 0.0)
    ra, rb = _type_rank(a), _type_rank(b)
    if ra != rb:
        x, y = ra, rb
    elif ra == 1:
        x, y = a.lower(), b.lower()
    elif ra == 0:
        x, y = float(a), float(b)
    else:
        x, y = a, b
    return {
        "=": x == y, "<>": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y,
    }[op]


def flatten(v):
    if isinstance(v, RangeValue):
        for row in v.rows:
            for item in row:
                yield item, True
    else:
        yield v, False


class RangeValue:
    __slots__ = ("rows",)

    def __init__(self, rows):
        self.rows = rows

    @property
    def height(self):
        return len(self.rows)

    @property
    def width(self):
        return len(self.rows[0]) if self.rows else 0


WILDCARD_CACHE = {}


def make_criteria(crit):
    """Return predicate for SUMIF/COUNTIF criteria."""
    if isinstance(crit, XLError):
        raise crit
    if is_number(crit) or isinstance(crit, bool):
        target = crit
        return lambda v: v is not None and v != "" and _safe_cmp(v, target, "=")
    s = to_text(crit)
    op = "="
    for candidate in ("<=", ">=", "<>", "<", ">", "="):
        if s.startswith(candidate):
            op, s = candidate, s[len(candidate):]
            break
    try:
        num = float(s)
        target = num
    except ValueError:
        target = s
    if isinstance(target, str) and op in ("=", "<>") and ("*" in target or "?" in target):
        pattern = "^" + re.escape(target).replace(r"\*", ".*").replace(r"\?", ".") + "$"
        rx = re.compile(pattern, re.I | re.S)
        if op == "=":
            return lambda v: isinstance(v, str) and bool(rx.match(v))
        return lambda v: not (isinstance(v, str) and bool(rx.match(v)))
    if target == "" and op == "=":
        return lambda v: v is None or v == ""
    if target == "" and op == "<>":
        return lambda v: not (v is None or v == "")

    def pred(v):
        if v is None or v == "":
            return op == "<>"
        if isinstance(target, float) and not is_number(v):
            if isinstance(v, str):
                try:
                    vv = float(v)
                except ValueError:
                    return op == "<>"
                return _safe_cmp(vv, target, op)
            return op == "<>"
        if isinstance(target, str) and is_number(v):
            return op == "<>"
        return _safe_cmp(v, target, op)

    return pred


def _safe_cmp(a, b, op):
    try:
        return compare(a, b, op)
    except XLError:
        return False


# ------------------------------------------------------------------ functions
FUNCTION_NAMES = {
    "SUM": "SUM", "SUMA": "SUM",
    "AVERAGE": "AVERAGE", "PROMEDIO": "AVERAGE",
    "MIN": "MIN", "MAX": "MAX",
    "COUNT": "COUNT", "CONTAR": "COUNT",
    "COUNTA": "COUNTA", "CONTARA": "COUNTA",
    "IF": "IF", "SI": "IF",
    "SUMIF": "SUMIF", "SUMAR.SI": "SUMIF",
    "COUNTIF": "COUNTIF", "CONTAR.SI": "COUNTIF",
    "VLOOKUP": "VLOOKUP", "BUSCARV": "VLOOKUP",
    "XLOOKUP": "XLOOKUP", "BUSCARX": "XLOOKUP",
    "AND": "AND", "Y": "AND",
    "OR": "OR", "O": "OR",
    "NOT": "NOT", "NO": "NOT",
    "ROUND": "ROUND", "REDONDEAR": "ROUND",
    "ABS": "ABS",
    "IFERROR": "IFERROR", "SI.ERROR": "IFERROR",
}
LAZY = {"IF", "IFERROR"}


def _numbers(args, direct_coerce=True):
    for a in args:
        for v, from_range in flatten(a):
            if isinstance(v, XLError):
                raise v
            if from_range:
                if is_number(v):
                    yield float(v)
            else:
                if v is None:
                    continue
                yield to_number(v) if direct_coerce else v


def fn_sum(args):
    return sum(_numbers(args))


def fn_average(args):
    nums = list(_numbers(args))
    if not nums:
        raise DIV0
    return sum(nums) / len(nums)


def fn_min(args):
    nums = list(_numbers(args))
    return min(nums) if nums else 0.0


def fn_max(args):
    nums = list(_numbers(args))
    return max(nums) if nums else 0.0


def fn_count(args):
    n = 0
    for a in args:
        for v, from_range in flatten(a):
            if is_number(v):
                n += 1
            elif not from_range and isinstance(v, str):
                try:
                    float(v)
                    n += 1
                except ValueError:
                    pass
    return float(n)


def fn_counta(args):
    n = 0
    for a in args:
        for v, _ in flatten(a):
            if v is not None and v != "":
                n += 1
    return float(n)


def _as_range(v):
    if isinstance(v, RangeValue):
        return v
    if isinstance(v, XLError):
        raise v
    return RangeValue([[v]])


def fn_sumif(args):
    if len(args) not in (2, 3):
        raise VALUE
    rng = _as_range(args[0])
    pred = make_criteria(args[1])
    srng = _as_range(args[2]) if len(args) == 3 else rng
    total = 0.0
    for i, row in enumerate(rng.rows):
        for j, v in enumerate(row):
            if pred(v):
                if i < srng.height and j < srng.width:
                    sv = srng.rows[i][j]
                    if isinstance(sv, XLError):
                        raise sv
                    if is_number(sv):
                        total += float(sv)
    return total


def fn_countif(args):
    if len(args) != 2:
        raise VALUE
    rng = _as_range(args[0])
    pred = make_criteria(args[1])
    return float(sum(1 for row in rng.rows for v in row if pred(v)))


def _lookup_equal(a, b):
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    if is_number(a) and is_number(b):
        return float(a) == float(b)
    return a == b


def fn_vlookup(args):
    if len(args) not in (3, 4):
        raise VALUE
    value, table = args[0], _as_range(args[1])
    if isinstance(value, XLError):
        raise value
    col = int(to_number(args[2]))
    approx = True if len(args) == 3 or args[3] is None else to_bool(args[3])
    if col < 1:
        raise VALUE
    if col > table.width:
        raise REF
    if not approx:
        for row in table.rows:
            if _lookup_equal(row[0], value):
                return row[col - 1]
        raise NA
    found = None
    for row in table.rows:
        key = row[0]
        if key is None:
            continue
        if _type_rank(key) != _type_rank(value):
            continue
        if compare(key, value, "<="):
            found = row
        else:
            break
    if found is None:
        raise NA
    return found[col - 1]


def fn_xlookup(args):
    if len(args) < 3 or len(args) > 5:
        raise VALUE
    value = args[0]
    if isinstance(value, XLError):
        raise value
    look, ret = _as_range(args[1]), _as_range(args[2])
    if len(args) == 5 and args[4] is not None and to_number(args[4]) != 0:
        raise VALUE  # only exact match (match_mode 0) is supported
    vertical = look.width == 1
    items = [r[0] for r in look.rows] if vertical else list(look.rows[0])
    for idx, key in enumerate(items):
        if _lookup_equal(key, value):
            if vertical:
                if idx >= ret.height:
                    raise VALUE
                row = ret.rows[idx]
                return row[0] if len(row) == 1 else RangeValue([row])
            if idx >= ret.width:
                raise VALUE
            col = [r[idx] for r in ret.rows]
            return col[0] if len(col) == 1 else RangeValue([[c] for c in col])
    if len(args) >= 4 and args[3] is not None:
        return args[3]
    raise NA


def fn_and(args):
    vals = [to_bool(v) for a in args for v, fr in flatten(a) if not (fr and (v is None or isinstance(v, str)))]
    if not vals:
        raise VALUE
    return all(vals)


def fn_or(args):
    vals = [to_bool(v) for a in args for v, fr in flatten(a) if not (fr and (v is None or isinstance(v, str)))]
    if not vals:
        raise VALUE
    return any(vals)


def fn_not(args):
    if len(args) != 1:
        raise VALUE
    return not to_bool(args[0])


def fn_round(args):
    if len(args) not in (1, 2):
        raise VALUE
    x = to_number(args[0])
    digits = int(to_number(args[1])) if len(args) == 2 else 0
    q = Decimal(1).scaleb(-digits)
    from decimal import ROUND_HALF_UP

    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP)) if digits >= 0 else float(
        (Decimal(repr(x)) / Decimal(10) ** (-digits)).quantize(Decimal(1), rounding=ROUND_HALF_UP) * Decimal(10) ** (-digits))


def fn_abs(args):
    if len(args) != 1:
        raise VALUE
    return abs(to_number(args[0]))


FUNCS = {
    "SUM": fn_sum, "AVERAGE": fn_average, "MIN": fn_min, "MAX": fn_max, "COUNT": fn_count, "COUNTA": fn_counta,
    "SUMIF": fn_sumif, "COUNTIF": fn_countif, "VLOOKUP": fn_vlookup, "XLOOKUP": fn_xlookup,
    "AND": fn_and, "OR": fn_or, "NOT": fn_not, "ROUND": fn_round, "ABS": fn_abs,
}


# ------------------------------------------------------------------ evaluator
class Workbook:
    """Evaluation context.

    ``sheets`` maps sheet name -> {(row, col): content}; content is either a
    python value (number/str/bool/None) or a string starting with "=" (formula).
    """

    def __init__(self, sheets, max_depth=4000):
        self.sheets = sheets
        self.lower_names = {name.lower(): name for name in sheets}
        self.cache = {}
        self.visiting = set()
        self.parsed = {}
        self.max_depth = max_depth
        self.depth = 0

    def resolve_sheet(self, name, default):
        if name is None:
            return default
        real = self.lower_names.get(name.lower())
        if real is None:
            raise REF
        return real

    def raw(self, sheet, r, c):
        return self.sheets[sheet].get((r, c))

    def value(self, sheet, r, c):
        key = (sheet, r, c)
        if key in self.cache:
            v = self.cache[key]
            if isinstance(v, XLError):
                return v
            return v
        raw = self.raw(sheet, r, c)
        if not (isinstance(raw, str) and raw.startswith("=")):
            return raw
        if key in self.visiting:
            raise _Circular(key)
        self.visiting.add(key)
        self.depth += 1
        try:
            if self.depth > self.max_depth:
                result = XLError("#NUM!")
            else:
                result = self.evaluate_formula(raw[1:], sheet, key)
        except _Circular as circ:
            self.cache[key] = CIRC
            self.visiting.discard(key)
            self.depth -= 1
            if circ.origin == key:
                return CIRC
            raise
        self.visiting.discard(key)
        self.depth -= 1
        self.cache[key] = result
        return result

    def evaluate_formula(self, text, sheet, key=None):
        node = self.parsed.get(key) if key else None
        if node is None:
            try:
                node = parse_formula(text)
            except FormulaSyntaxError:
                return NAME if re.search(r"[A-Za-z]", text) else VALUE
            if key:
                self.parsed[key] = node
        try:
            result = self.ev(node, sheet)
            if isinstance(result, RangeValue):
                result = result.rows[0][0] if result.rows and result.rows[0] else None
            if isinstance(result, float) and (math.isnan(result) or math.isinf(result)):
                return NUM
            return result
        except XLError as err:
            return err
        except RecursionError:
            return NUM

    def ev(self, node, sheet):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return node[1]
        if kind == "bool":
            return node[1]
        if kind == "err":
            raise node[1]
        if kind == "empty":
            return None
        if kind == "name":
            raise NAME
        if kind == "ref":
            ref = node[1]
            target = self.resolve_sheet(ref.sheet, sheet)
            if ref.r2 >= MAX_ROWS or ref.c2 >= MAX_COLS:
                raise REF
            if not ref.is_range:
                v = self.value(target, ref.r1, ref.c1)
                if isinstance(v, XLError):
                    raise v
                return v
            if (ref.r2 - ref.r1 + 1) * (ref.c2 - ref.c1 + 1) > 2_000_000:
                raise VALUE
            rows = []
            # clamp to used area for efficiency
            used = self.sheets[target]
            max_r = max((k[0] for k in used), default=-1)
            r2 = min(ref.r2, max_r)
            for r in range(ref.r1, r2 + 1):
                rows.append([self.value(target, r, c) for c in range(ref.c1, ref.c2 + 1)])
            if not rows:
                rows = [[None] * (ref.c2 - ref.c1 + 1)]
            return RangeValue(rows)
        if kind == "neg":
            return -to_number(self.scalar(node[1], sheet))
        if kind == "pos":
            return to_number(self.scalar(node[1], sheet))
        if kind == "pct":
            return to_number(self.scalar(node[1], sheet)) / 100
        if kind == "bin":
            op = node[1]
            a = self.scalar(node[2], sheet)
            b = self.scalar(node[3], sheet)
            if op == "&":
                return to_text(a) + to_text(b)
            if op in ("=", "<>", "<", ">", "<=", ">="):
                return compare(a, b, op)
            x, y = to_number(a), to_number(b)
            if op == "+":
                return x + y
            if op == "-":
                return x - y
            if op == "*":
                return x * y
            if op == "/":
                if y == 0:
                    raise DIV0
                return x / y
            if op == "^":
                try:
                    r = x ** y
                except (OverflowError, ZeroDivisionError):
                    raise NUM
                if isinstance(r, complex):
                    raise NUM
                return r
        if kind == "call":
            name = FUNCTION_NAMES.get(node[1])
            if name is None:
                raise NAME
            args = node[2]
            if name == "IF":
                if len(args) < 2 or len(args) > 3:
                    raise VALUE
                cond = to_bool(self.scalar(args[0], sheet))
                if cond:
                    return self.ev(args[1], sheet) if args[1][0] != "empty" else 0.0
                if len(args) == 3:
                    return self.ev(args[2], sheet) if args[2][0] != "empty" else 0.0
                return False
            if name == "IFERROR":
                if len(args) != 2:
                    raise VALUE
                try:
                    v = self.ev(args[0], sheet)
                    if isinstance(v, XLError):
                        raise v
                    return v
                except XLError:
                    return self.ev(args[1], sheet)
            values = [self.ev(a, sheet) for a in args]
            return FUNCS[name](values)
        raise VALUE

    def scalar(self, node, sheet):
        v = self.ev(node, sheet)
        if isinstance(v, RangeValue):
            if v.height == 1 and v.width == 1:
                return v.rows[0][0]
            raise VALUE
        return v


class _Circular(Exception):
    def __init__(self, origin):
        super().__init__("circular")
        self.origin = origin


def evaluate_workbook(sheets):
    """Compute every formula cell. Returns {(sheet, r, c): value} for formula cells."""
    wb = Workbook(sheets)
    out = {}
    for sheet, cells in sheets.items():
        for (r, c), raw in sorted(cells.items()):
            if isinstance(raw, str) and raw.startswith("="):
                try:
                    v = wb.value(sheet, r, c)
                except _Circular:
                    v = CIRC
                    wb.cache[(sheet, r, c)] = CIRC
                out[(sheet, r, c)] = v
    return out


def referenced_functions(formula_text):
    try:
        toks = tokenize(formula_text)
    except FormulaSyntaxError:
        return set()
    return {t.value.upper() for t in toks if t.kind == "func"}


def unsupported_functions(formula_text):
    return {f for f in referenced_functions(formula_text) if f not in FUNCTION_NAMES}


# ------------------------------------------------------------------ reference rewriting
def _fmt_cell(abs_c, col, abs_r, row):
    return f"{'$' if abs_c else ''}{index_to_col(col)}{'$' if abs_r else ''}{row + 1}"


def _rewrite_refs(formula, func):
    """Apply func(sheet_prefix, cells[(abs_c, col, abs_r, row)...], sheet_name) -> str|None to each ref token."""
    if not formula.startswith("="):
        return formula
    body = formula[1:]
    try:
        toks = tokenize(body)
    except FormulaSyntaxError:
        return formula
    out, last = [], 0
    for t in toks:
        if t.kind != "ref":
            continue
        prefix = ""
        text = t.value
        if "!" in text:
            prefix, addr = text.rsplit("!", 1)
            prefix += "!"
        else:
            addr = text
        cells = []
        for part in addr.split(":"):
            m = CELL_RE.match(part)
            cells.append((bool(m.group(1)), col_to_index(m.group(2)), bool(m.group(3)), int(m.group(4)) - 1))
        sheet_name = split_sheet(text)[0]
        replacement = func(prefix, cells, sheet_name)
        out.append(body[last:t.start])
        out.append(replacement if replacement is not None else text)
        last = t.end
    out.append(body[last:])
    return "=" + "".join(out)


def shift_formula(formula, drow, dcol):
    """Relative references move by (drow, dcol) like Excel copy/paste; absolute parts stay."""

    def func(prefix, cells, _sheet):
        parts = []
        for abs_c, col, abs_r, row in cells:
            nc = col if abs_c else col + dcol
            nr = row if abs_r else row + drow
            if nc < 0 or nr < 0:
                return "#REF!"
            parts.append(_fmt_cell(abs_c, nc, abs_r, nr))
        return prefix + ":".join(parts)

    return _rewrite_refs(formula, func)


def adjust_structure(formula, formula_sheet, target_sheet, axis, index, count):
    """Adjust references after inserting (count>0) or deleting (count<0) rows/cols at index
    in target_sheet. Deleted single references become #REF!; ranges shrink."""

    def move(pos):
        if count > 0:
            return pos + count if pos >= index else pos
        removed_end = index - count  # exclusive
        if pos >= removed_end:
            return pos + count
        if pos >= index:
            return None
        return pos

    def func(prefix, cells, sheet_name):
        ref_sheet = sheet_name if sheet_name is not None else formula_sheet
        if ref_sheet.lower() != target_sheet.lower():
            return None
        if len(cells) == 1:
            abs_c, col, abs_r, row = cells[0]
            pos = row if axis == "row" else col
            new = move(pos)
            if new is None:
                return "#REF!"
            if axis == "row":
                return prefix + _fmt_cell(abs_c, col, abs_r, new)
            return prefix + _fmt_cell(abs_c, new, abs_r, row)
        (ac1, c1, ar1, r1), (ac2, c2, ar2, r2) = cells
        p1, p2 = (r1, r2) if axis == "row" else (c1, c2)
        if count > 0:
            n1, n2 = move(p1), (p2 + count if p2 >= index else p2)
        else:
            removed_end = index - count
            n1 = p1 if p1 < index else (index if p1 < removed_end else p1 + count)
            n2 = p2 + count if p2 >= removed_end else (index - 1 if p2 >= index else p2)
            if n2 < n1:
                return "#REF!"
        if axis == "row":
            return prefix + _fmt_cell(ac1, c1, ar1, n1) + ":" + _fmt_cell(ac2, c2, ar2, n2)
        return prefix + _fmt_cell(ac1, n1, ar1, r1) + ":" + _fmt_cell(ac2, n2, ar2, r2)

    return _rewrite_refs(formula, func)


def quote_sheet(name):
    if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", name) and not CELL_RE.match(name):
        return name
    return "'" + name.replace("'", "''") + "'"


def rename_sheet_refs(formula, old, new):
    def func(prefix, cells, sheet_name):
        if sheet_name is None or sheet_name.lower() != old.lower():
            return None
        addr = ":".join(_fmt_cell(*c) for c in cells)
        return f"{quote_sheet(new)}!{addr}"

    return _rewrite_refs(formula, func)


def sheets_referenced(formula):
    names = set()
    if not formula.startswith("="):
        return names
    try:
        for t in tokenize(formula[1:]):
            if t.kind == "ref" and "!" in t.value:
                names.add(split_sheet(t.value)[0])
    except FormulaSyntaxError:
        pass
    return names
