"""Conservative local matching against a versioned synthetic distributor catalogue."""

import re
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

Record = dict[str, Any]
VERSION = "SYN-2026-11-18"
CENT = Decimal("0.01")
GST_RATE = Decimal("0.15")
MAX_QUANTITY = 9999


@dataclass(frozen=True)
class Part:
    sku: str
    family: str
    name: str
    specs: dict[str, str]
    stock: int
    price: str
    discontinued: bool = False


def _cylinder(bore: int, stroke: int) -> dict[str, str]:
    return {
        "bore": f"{bore} mm",
        "stroke": f"{stroke} mm",
        "action": "double acting",
        "standard": "ISO 15552",
        "port": "G1/8",
        "mount": "foot mount",
    }


def _bearing(seal: str) -> dict[str, str]:
    return {
        "bore": "25 mm",
        "outside diameter": "52 mm",
        "width": "15 mm",
        "closure": seal,
    }


PARTS = (
    Part(
        "CYL-32-100-DA",
        "Pneumatic cylinder",
        "ISO cylinder · 32 × 100 mm",
        _cylinder(32, 100),
        12,
        "155.00",
    ),
    Part(
        "CYL-32-160-DA",
        "Pneumatic cylinder",
        "ISO cylinder · 32 × 160 mm",
        _cylinder(32, 160),
        4,
        "178.50",
    ),
    Part(
        "CYL-40-100-DA",
        "Pneumatic cylinder",
        "ISO cylinder · 40 × 100 mm",
        _cylinder(40, 100),
        5,
        "184.00",
    ),
    Part(
        "CYL-32-OLD",
        "Pneumatic cylinder",
        "Legacy 32 mm cylinder",
        {**_cylinder(32, 100), "mount": "clevis mount"},
        0,
        "140.00",
        True,
    ),
    Part(
        "BRG-6205-2RS",
        "Bearing",
        "6205 sealed deep-groove bearing",
        _bearing("rubber seals"),
        72,
        "12.75",
    ),
    Part(
        "BRG-6205-ZZ",
        "Bearing",
        "6205 shielded deep-groove bearing",
        _bearing("metal shields"),
        20,
        "11.50",
    ),
    Part(
        "BLT-M12-80",
        "Fastener",
        "M12 × 80 hex bolt · grade 8.8",
        {"thread": "M12", "length": "80 mm", "pitch": "1.75 mm", "grade": "8.8"},
        125,
        "3.90",
    ),
    Part(
        "ADP-BSPP-14",
        "Hydraulic adapter",
        "Parallel hydraulic nipple · ¼ in BSPP",
        {
            "thread": "BSPP",
            "size": "1/4 in",
            "pressure": "250 bar",
            "connection": "male to male",
        },
        8,
        "19.95",
    ),
    Part(
        "ADP-NPT-14",
        "Hydraulic adapter",
        "Tapered hydraulic nipple · ¼ in NPT",
        {
            "thread": "NPT",
            "size": "1/4 in",
            "pressure": "200 bar",
            "connection": "male to male",
        },
        0,
        "21.50",
    ),
)
BY_SKU = {p.sku: p for p in PARTS}
# Explicit net rates from the synthetic account agreement. Some agreements forbid fallback.
CONTRACTS = {
    "harbour packaging": {"CYL-32-100-DA": "137.50"},
    "contract only engineering": {},
}
CONTRACT_ONLY = {"contract only engineering"}
FAMILIES = {
    "Pneumatic cylinder": r"(?:pneumatic\s+)?cylinders?",
    "Bearing": r"(?:deep[- ]groove\s+)?bearings?",
    "Fastener": r"(?:hex\s+)?bolts?|fasteners?",
    "Hydraulic adapter": r"(?:hydraulic\s+)?(?:adapt[eo]rs?|nipples?|fittings?)",
}
PREFIXES = {
    "CYL": "Pneumatic cylinder",
    "BRG": "Bearing",
    "BLT": "Fastener",
    "ADP": "Hydraulic adapter",
}
REFERENCE = re.compile(r"(?<![\w-])(?:CYL|BRG|BLT|ADP)-[\w-]+(?![\w-])", re.IGNORECASE)
WORDS = dict(
    zip(
        ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"],
        range(1, 11),
    )
)
COUNT = r"(?:[+-]?\d+(?:\.\d+)?|" + "|".join(WORDS) + ")"
NOUN = "(?:" + "|".join(FAMILIES.values()) + ")"
QUANTITY = re.compile(
    rf"(?<![\w./+-])({COUNT})\s*(?:[x×](?![a-z])|(?:off|pcs|pieces|units)\b|(?=(?:replacement\s+)?{NOUN}\b)|(?=(?:cyl|brg|blt|adp)-))"
    rf"|\b(?:qty|quantity)\s*[:=]?\s*({COUNT})\b",
    re.IGNORECASE,
)
LABEL = {
    "action": "acting type (single or double)",
    "standard": "cylinder standard",
    "port": "port thread",
    "mount": "mount type",
    "closure": "seal or shield type",
    "connection": "end connections",
    "pressure": "required working pressure",
}
# Only understood requirements are eligible for verification. Unconsumed language goes to review.
COURTESY = re.compile(
    r"\b(?:hi|hello|please|thanks|thank you|we urgently need|we need|i need|need|urgent(?:ly)?|"
    r"could you (?:please )?quote|quote(?: for)?|replacement|as shown in the attachment|"
    r"for our packaging machine|the label has worn off|label unreadable|"
    r"and|with|units)\b",
    re.IGNORECASE,
)
HIGH_RISK = re.compile(
    r"\b(?:approve|ignore|override|personnel|lifting|brake|safety|medical|oxygen|"
    r"not|instead|unless|except|either|or|if|alternative|maybe|approximately)\b",
    re.IGNORECASE,
)


def _commercial(part: Part, account: str) -> Record:
    customer = account.strip().casefold()
    contract_price = CONTRACTS.get(customer, {}).get(part.sku)
    price = contract_price or (None if customer in CONTRACT_ONLY else part.price)
    availability = (
        "Discontinued"
        if part.discontinued
        else (
            f"{part.stock} on hand"
            if part.stock
            else "Special order · supplier availability unknown"
        )
    )
    return {
        "stock": part.stock,
        "availability": availability,
        "unit_price": price,
        "price_basis": "Account agreement"
        if contract_price
        else ("List price" if price else "Contract price missing"),
        "delivery": "Delivery date unconfirmed",
        "commercial_source": f"Synthetic stock and price book / {VERSION}",
    }


def _candidate(part: Part, account: str, evidence: list[str]) -> Record:
    return {
        "sku": part.sku,
        "name": part.name,
        "family": part.family,
        "specs": dict(part.specs),
        "source": f"Synthetic catalogue / {VERSION} / {part.sku}",
        "evidence": evidence,
        "discontinued": part.discontinued,
        **_commercial(part, account),
    }


def current_record(sku: str, account: str = "") -> Record | None:
    part = BY_SKU.get(sku)
    return _candidate(part, account, []) if part else None


def catalogue(account: str = "") -> list[Record]:
    return [_candidate(p, account, []) for p in BY_SKU.values()]


def _line_texts(text: str) -> list[tuple[str, bool]]:
    # A bare measurement or quantity can complete a single request. After multiple
    # items, a continuation has ambiguous scope until the customer identifies it.
    normal = re.sub(r"[^\S\n]+", " ", text)
    starter = (
        rf"(?:{COUNT} +)?(?:[x×] *|(?:replacement +)?{NOUN}\b|(?:cyl|brg|blt|adp)-)"
    )
    paragraphs = re.split(
        rf"[\n;]+|, *(?={NOUN}\b)| +(?:and|plus|also|with) +(?={starter})",
        normal,
        flags=re.IGNORECASE,
    )
    groups: list[list[str]] = []
    ambiguous: set[int] = set()
    current_has_item = False
    for paragraph in paragraphs:
        chunk = paragraph.strip()
        if not chunk:
            continue
        quantity = QUANTITY.search(chunk)
        only_quantity = quantity and not QUANTITY.sub("", chunk).strip(" .,!")
        starts_item = bool(
            REFERENCE.search(chunk)
            or re.match(NOUN + r"\b", chunk, re.IGNORECASE)
            or (quantity and not only_quantity)
        )
        if not groups or (current_has_item and starts_item):
            groups.append([chunk])
            current_has_item = starts_item
        else:
            groups[-1].append(chunk)
            current_has_item = current_has_item or starts_item
            if len(groups) > 1:
                ambiguous.add(len(groups) - 1)
        if len(groups) > 100:
            raise ValueError("Process at most 100 catalogue line items per enquiry.")
    return [(" ".join(chunks), i in ambiguous) for i, chunks in enumerate(groups)] or [
        ("", False)
    ]


def _count(text: str) -> tuple[int | None, str]:
    matches = list(QUANTITY.finditer(text))
    values = [m.group(1) or m.group(2) for m in matches]
    counts = {
        WORDS[v] if v in WORDS else int(v)
        for v in values
        if v in WORDS or (v.isascii() and v.isdigit() and len(v) <= 4)
    }
    quantity = counts.pop() if len(counts) == 1 and len(values) == 1 else None
    return (
        quantity if quantity and 1 <= quantity <= MAX_QUANTITY else None
    ), QUANTITY.sub(" ", text)


def _attributes(text: str) -> tuple[dict[str, str], set[str], str]:
    found: dict[str, set[str]] = {}
    residual = text

    def capture(
        field: str, pattern: str, suffix: str = "", fixed: str | None = None
    ) -> None:
        nonlocal residual

        def substitute(m: re.Match[str]) -> str:
            if fixed is None:
                number = next(s for s in m.groups() if s is not None)
                if suffix:
                    # Strip formatting zeros without rounding a measurement to decimal context precision.
                    number = format(Decimal(number), "f")
                    if "." in number:
                        number = number.rstrip("0").rstrip(".")
                value = number + suffix
            else:
                value = fixed
            found.setdefault(field, set()).add(value)
            return " "

        residual = re.sub(pattern, substitute, residual, flags=re.IGNORECASE)

    dimension = r"(\d+(?:\.\d+)?)\s*mm\b"
    for key, label in (
        ("bore", "bore"),
        ("stroke", "stroke"),
        ("width", "width"),
        ("outside diameter", "(?:outside diameter|OD)"),
        ("length", "length"),
        ("pitch", "pitch"),
    ):
        capture(
            key,
            rf"\b{label}\s*[:=]?\s*{dimension}|(?<![\w./+-]){dimension}\s*{label}\b",
            " mm",
        )
    for field, forms in {
        "action": ["double acting", "single acting"],
        "mount": ["foot mount", "clevis mount", "flange mount"],
        "closure": ["metal shields", "rubber seals"],
        "connection": ["male to male", "female to female", "male to female"],
        "thread": ["BSPP", "BSPT", "NPT", "M12"],
    }.items():
        for form in forms:
            capture(
                field,
                r"\b"
                + form.replace(" ", r"[ -]")
                + (r"(?:\s+thread)?\b" if field == "thread" else r"\b"),
                fixed=form,
            )
    capture("standard", r"\biso\s*15552\b", fixed="ISO 15552")
    capture("port", r"\bg\s*1/8\b(?:\s+ports?\b)?", fixed="G1/8")
    capture("port", r"\bg\s*1/4\b(?:\s+ports?\b)?", fixed="G1/4")
    capture(
        "pressure",
        r"(?<![\w./+-])(?:(?:working )?pressure\s*[:=]?\s*)?(\d+(?:\.\d+)?)\s*bar\b",
        " bar",
    )
    capture("size", r'(?<![\w/])1/4\s*(?:in(?:ch(?:es)?)?\b|")', fixed="1/4 in")
    capture("grade", r"\bgrade\s+(\d+\.\d+)\b")
    return (
        {k: " / ".join(sorted(v)) for k, v in found.items()},
        {k for k, v in found.items() if len(v) > 1},
        residual,
    )


def _compatible(key: str, value: str, part: Part) -> bool:
    spec = part.specs.get(key)
    if key == "pressure" and spec:
        return Decimal(0) < Decimal(value.split()[0]) <= Decimal(spec.split()[0])
    return value == spec


def _analyse_line(text: str, account: str, ambiguous: bool) -> Record:
    normal = text.lower().replace("–", "-").replace("‑", "-")
    references = [m.group().upper() for m in REFERENCE.finditer(normal)]
    families = {
        f
        for f, pattern in FAMILIES.items()
        if re.search(r"\b(?:" + pattern + r")\b", normal)
    }
    families.update(PREFIXES[ref.split("-", 1)[0]] for ref in references)
    family = next(iter(families)) if len(families) == 1 else "Unidentified"
    quantity, residual = _count(normal)
    residual = REFERENCE.sub(" ", residual)
    for pattern in FAMILIES.values():
        residual = re.sub(r"\b(?:" + pattern + r")\b", " ", residual)
    attrs, contradictory, residual = _attributes(residual)
    unparsed = COURTESY.sub(" ", residual).strip()
    unknown_words = bool(re.search(r"[^\s,.:;!?()]", unparsed))
    ref = references[0] if len(references) == 1 else None
    part = BY_SKU.get(ref or "")
    pool = (
        [part]
        if part
        else [p for p in BY_SKU.values() if p.family == family and not p.discontinued]
    )
    candidates, compatible = [], []
    for product in pool:
        evidence = (
            ["Exact synthetic distributor reference"]
            if product == part
            else ["Same component family"]
        )
        for field, value in attrs.items():
            spec = product.specs.get(field, "unlisted")
            verdict = (
                "Meets"
                if field not in contradictory and _compatible(field, value, product)
                else "Conflict"
            )
            evidence.append(f"{verdict} · {field}: requested {value}, catalogue {spec}")
        if all(_compatible(k, v, product) for k, v in attrs.items()):
            compatible.append(product)
        candidates.append(_candidate(product, account, evidence))

    issues: list[str] = []
    questions: list[str] = []
    missing = [] if part or not pool else [k for k in pool[0].specs if k not in attrs]
    if quantity is None:
        questions.append("What whole-unit quantity is required for this item?")
    if missing:
        questions.append(
            "Please confirm the " + ", ".join(LABEL.get(k, k) for k in missing) + "."
        )
    if (
        contradictory
        or len(families) > 1
        or len(references) > 1
        or (pool and not compatible)
    ):
        status = "conflict"
        issues.append(
            "Conflicting specifications or references. "
            + ", ".join(sorted(contradictory))
        )
        questions.append(
            "Please confirm which specifications and reference apply to this item."
        )
    elif (part and part.discontinued) or HIGH_RISK.search(normal):
        status = "review"
        issues.append(
            "Discontinued reference or a condition requiring employee review."
        )
        questions.append(
            "Please confirm the intended service and any special conditions with a technical reviewer."
        )
    elif (references and not part) or not pool:
        status = "clarify"
        issues.append("No exact record for the supplied reference or family.")
        questions.append(
            "Can you provide the full distributor reference or a readable nameplate?"
        )
    elif ambiguous:
        status = "review"
        issues.append("A follow-up detail could apply to more than one requested item.")
        questions.append(
            "Which reference does the additional specification or quantity apply to?"
        )
    elif not missing and ("as shown in the attachment" in normal or "?" in normal):
        status = "review"
        issues.append(
            "A reference or specification depends on a question or unreviewed attachment."
        )
        questions.append(
            "Please confirm the exact item and verify any attachment requirements."
        )
    elif unknown_words:
        status = "review"
        issues.append(
            "Requirement outside the supported catalogue checks: "
            + " ".join(unparsed.split())[:180]
        )
        questions.append(
            "Please confirm the additional wording and required specifications with a technical reviewer."
        )
    elif missing or quantity is None or len(compatible) != 1:
        status = "clarify"
        issues.append("Additional information is required to identify this item.")
    else:
        status = "verified"
    sku = compatible[0].sku if status == "verified" else None
    if sku and quantity:
        commercial = _commercial(BY_SKU[sku], account)
        if quantity > commercial["stock"]:
            issues.append(
                "Insufficient confirmed stock. Supplier availability and delivery are unconfirmed."
            )
        if commercial["unit_price"] is None:
            issues.append("No authorised price is available for this account.")
    return {
        "family": family,
        "quantity": quantity,
        "attributes": attrs,
        "reference": ref,
        "status": status,
        "sku": sku,
        "candidates": candidates,
        "questions": questions,
        "issues": issues,
        "text": text,
    }


def analyse(text: str, account: str = "") -> Record:
    if not isinstance(text, str) or len(text) > 65536:
        raise ValueError("Supply enquiry text up to 65,536 characters.")
    lines = [
        _analyse_line(chunk, account, ambiguous)
        for chunk, ambiguous in _line_texts(text)
    ]
    if len(lines) > 1 and re.search(r"\b(?:each|per|apiece)\b", text, re.IGNORECASE):
        for line in lines:
            line.update(status="review", sku=None, quantity=None)
            line["issues"].append(
                "The quantities may be per assembly rather than totals."
            )
            line["questions"].append(
                "Please confirm the total quantity of each reference across all assemblies."
            )
    requested: Counter[str] = Counter()
    for line in lines:
        if line["sku"]:
            requested[line["sku"]] += line["quantity"]
    for line in lines:
        sku = line["sku"]
        if sku and requested[sku] > BY_SKU[sku].stock and not line["issues"]:
            line["issues"].append(
                "Combined quantity exceeds confirmed stock for this reference."
            )
    return {
        "lines": lines,
        "ready": all(
            line["status"] == "verified" and not line["issues"] for line in lines
        ),
        "questions": list(
            dict.fromkeys(q for line in lines for q in line["questions"])
        ),
        "urgent": bool(
            re.search(
                r"\b(urgent(?:ly)?|breakdown|broken down|machine down)\b",
                text,
                re.IGNORECASE,
            )
        ),
    }


def build_quote(
    analysis: Record, account: str = "", quantities: dict[str, int] | None = None
) -> Record:
    """Price an entire verified enquiry. Callers supply analysis derived server-side."""
    if not analysis.get("ready") or not analysis.get("lines"):
        raise ValueError("Resolve every technical and commercial issue before quoting.")
    requested: Counter[str] = Counter()
    for line in analysis["lines"]:
        sku, qty = line["sku"], line["quantity"]
        if (
            line["status"] != "verified"
            or sku not in BY_SKU
            or type(qty) is not int
            or qty < 1
        ):
            raise ValueError("Invalid verified quotation line.")
        requested[sku] += qty
    original_quantities = requested.copy()
    if quantities is not None:
        if not isinstance(quantities, dict) or quantities.keys() - requested.keys():
            raise ValueError("Quantities may only edit verified references.")
        for sku, qty in quantities.items():
            if type(qty) is not int or not 1 <= qty <= MAX_QUANTITY:
                raise ValueError("Enter a positive whole-unit quantity.")
            requested[sku] = qty
    subtotal = Decimal("0.00")
    lines = []
    for sku, quantity in requested.items():
        part = BY_SKU[sku]
        commercial = _commercial(part, account)
        if (
            part.discontinued
            or quantity > part.stock
            or commercial["unit_price"] is None
        ):
            raise ValueError("Confirmed stock and authorised pricing are required.")
        extended = Decimal(commercial["unit_price"]) * quantity
        subtotal += extended
        lines.append(
            {
                "sku": sku,
                "name": part.name,
                "quantity": quantity,
                "line_total": str(extended),
                "requested_quantity": original_quantities[sku],
                **commercial,
            }
        )
    gst = (subtotal * GST_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "lines": lines,
        "currency": "NZD",
        "subtotal": str(subtotal),
        "gst": str(gst),
        "total": str(subtotal + gst),
        "gst_rate": str(GST_RATE),
    }
