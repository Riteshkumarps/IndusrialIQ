import re
from typing import Dict, Any, Iterable, Optional


def clean_text(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None

    placeholders = {
        "-- Unbranded --",
        "-- No Unilog Brand --",
        "-- No DIB Brand --",
        "nan",
        "none",
        "null",
        "n/a",
    }

    if value.lower() in {x.lower() for x in placeholders}:
        return None

    return re.sub(r"\s+", " ", value)


def normalize_uom(value: str) -> str:
    if not value:
        return value

    s = str(value).strip()

    replacements = [
        (r'(?i)(\d+(?:\.\d+)?)\s*(?:inches|inch|in\.|\")\b', r'\1 in'),
        (r'(?i)(\d+(?:\.\d+)?)\s*lbs?\b', r'\1 lb'),
        (r'(?i)(\d+(?:\.\d+)?)\s*pounds?\b', r'\1 lb'),
        (r'(?i)(\d+(?:\.\d+)?)\s*volts?\b', r'\1 V'),
        (r'(?i)(\d+(?:\.\d+)?)\s*amps?\b', r'\1 A'),
        (r'(?i)(\d+(?:\.\d+)?)\s*hours?\b', r'\1 hr'),
    ]

    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s)

    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_text_units(text: str) -> str:
    if not text:
        return ""

    text = re.sub(
        r'(\d+(?:\.\d+)?)\s*(?:inches|inch|in\.|\")',
        r'\1 in',
        text,
        flags=re.I,
    )
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def within_limit(text: str, minimum=None, maximum=None) -> bool:
    n = len(text or "")
    if minimum is not None and n < minimum:
        return False
    if maximum is not None and n > maximum:
        return False
    return True


def _norm(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    text = _norm(text)
    return any(_norm(term) in text for term in terms)


def build_manufacturer_brand_map(manufacturer_df) -> Dict[str, set]:
    """Build manufacturer -> allowed brands from the master reference table."""
    mapping: Dict[str, set] = {}
    if manufacturer_df is None or getattr(manufacturer_df, "empty", True):
        return mapping

    mcol = next((c for c in ["MANUFACTURER_NAME", "Manufacturer", "manufacturer"] if c in manufacturer_df.columns), None)
    bcol = next((c for c in ["BRAND_NAME", "Brand", "brand"] if c in manufacturer_df.columns), None)
    if not mcol or not bcol:
        return mapping

    for _, row in manufacturer_df[[mcol, bcol]].dropna().iterrows():
        manufacturer = _norm(row[mcol])
        brand = _norm(row[bcol])
        if manufacturer and brand:
            mapping.setdefault(manufacturer, set()).add(brand)
    return mapping


def _lookup_master_match(value: str, choices: Iterable[str]) -> Optional[str]:
    normalized = _norm(value)
    for choice in choices:
        if normalized and normalized == _norm(choice):
            return choice
    return None


def consistency_validate(product: Dict[str, Any], manufacturer_df=None, lov_df=None) -> Dict[str, Any]:
    """Cross-field validation that catches plausible-looking but incompatible data.

    This validator is deliberately conservative. A failed consistency rule sends the
    record to human review instead of silently correcting the value.
    """
    manufacturer = product.get("manufacturer") or ""
    brand = product.get("brand") or ""
    category = product.get("category") or ""
    description = product.get("raw_description") or ""
    product_type = product.get("product_type") or ""

    checks: Dict[str, bool] = {}
    issues = []

    # 1) Manufacturer <-> Brand relationship from the master.
    mapping = build_manufacturer_brand_map(manufacturer_df)
    mkey = _norm(manufacturer)
    bkey = _norm(brand)
    if manufacturer and brand and mapping:
        allowed = mapping.get(mkey)
        if allowed is None:
            checks["manufacturer_brand_master"] = False
            issues.append({
                "code": "UNKNOWN_MANUFACTURER_RELATION",
                "severity": "high",
                "message": f"Manufacturer '{manufacturer}' is not present in the manufacturer-brand relationship master.",
                "fields": ["manufacturer", "brand"],
            })
        else:
            ok = bkey in allowed
            checks["manufacturer_brand_master"] = ok
            if not ok:
                issues.append({
                    "code": "BRAND_MANUFACTURER_MISMATCH",
                    "severity": "high",
                    "message": f"Brand '{brand}' is not mapped to manufacturer '{manufacturer}' in the master data.",
                    "fields": ["manufacturer", "brand"],
                    "expected_brands": sorted(allowed),
                })
    else:
        checks["manufacturer_brand_master"] = True

    # 2) Category vs product text. This is a guardrail, not a hard classifier.
    category_rules = [
        ("built in dishwashers", ["dishwasher", "dish washer"]),
        ("faucets", ["faucet"]),
        ("fittings", ["fitting", "coupling", "elbow", "tee"]),
        ("line lasers", ["laser", "cross line"]),
        ("saw blades", ["saw blade"]),
        ("router bits", ["router bit"]),
        ("socket adapters", ["socket adapter"]),
        ("cut off discs", ["cut off disc", "cut-off disc"]),
    ]
    matched_rule = next((terms for cat, terms in category_rules if _norm(cat) == _norm(category)), None)
    if matched_rule:
        ok = _contains_any(description, matched_rule)
        checks["category_description_consistency"] = ok
        if not ok:
            issues.append({
                "code": "CATEGORY_DESCRIPTION_MISMATCH",
                "severity": "high",
                "message": f"Category '{category}' is not supported by the source description.",
                "fields": ["category", "raw_description"],
            })
    else:
        checks["category_description_consistency"] = True

    # 3) Product type / category consistency for common classes.
    type_rules = {
        "line lasers": ["laser", "laser level"],
        "cut off discs": ["disc", "disk", "cut off"],
        "built in dishwashers": ["dishwasher"],
        "faucets": ["faucet"],
    }
    terms = type_rules.get(_norm(category))
    if terms and product_type:
        ok = _contains_any(product_type, terms) or _contains_any(description, terms)
        checks["product_type_category_consistency"] = ok
        if not ok:
            issues.append({
                "code": "PRODUCT_TYPE_CATEGORY_MISMATCH",
                "severity": "medium",
                "message": f"Product type '{product_type}' is inconsistent with category '{category}'.",
                "fields": ["product_type", "category"],
            })
    else:
        checks["product_type_category_consistency"] = True

    # 4) Attribute applicability using the LOV table.
    attrs = product.get("attributes") or {}
    if lov_df is not None and not getattr(lov_df, "empty", True) and category:
        ccol = next((c for c in ["Leaf Node", "Category", "Classpath"] if c in lov_df.columns), None)
        acol = next((c for c in ["Attribute Label", "Attribute", "Attribute_Name"] if c in lov_df.columns), None)
        if ccol and acol:
            allowed_attrs = set()
            for _, row in lov_df.iterrows():
                if _norm(row.get(ccol)) == _norm(category) or _norm(category) in _norm(row.get(ccol)):
                    allowed_attrs.add(_norm(row.get(acol)))
            unexpected = [name for name in attrs if _norm(name) not in allowed_attrs and allowed_attrs]
            ok = not unexpected
            checks["attribute_category_consistency"] = ok
            if not ok:
                issues.append({
                    "code": "ATTRIBUTE_CATEGORY_MISMATCH",
                    "severity": "medium",
                    "message": "One or more attributes are not listed for this category in the LOV.",
                    "fields": ["attributes", "category"],
                    "unexpected_attributes": unexpected,
                })
        else:
            checks["attribute_category_consistency"] = True
    else:
        checks["attribute_category_consistency"] = True

    high = sum(1 for i in issues if i["severity"] == "high")
    medium = sum(1 for i in issues if i["severity"] == "medium")
    passed = sum(bool(v) for v in checks.values())
    total = len(checks)

    return {
        "checks": checks,
        "issues": issues,
        "issue_count": len(issues),
        "high_risk_count": high,
        "medium_risk_count": medium,
        "passed": passed,
        "total": total,
        "status": "PASS" if not issues else "REVIEW",
    }


def validate_product(
    product: Dict[str, Any],
    manufacturer_names: Iterable[str],
    brand_names: Iterable[str],
    allowed_categories: Iterable[str],
    manufacturer_df=None,
    lov_df=None,
) -> Dict:
    checks = {}

    manufacturers = {_norm(x) for x in manufacturer_names if x}
    brands = {_norm(x) for x in brand_names if x}
    categories = {_norm(x) for x in allowed_categories if x}

    manufacturer = _norm(product.get("manufacturer"))
    brand = _norm(product.get("brand"))
    category = _norm(product.get("category"))

    checks["manufacturer"] = bool(manufacturer) and (
        not manufacturers or manufacturer in manufacturers
    )
    checks["brand"] = bool(brand) and (
        not brands or brand in brands
    )
    checks["category"] = bool(category) and (
        not categories or category in categories
    )

    checks["title_length"] = 0 < len(product.get("title", "")) <= 200
    checks["description_length"] = 0 < len(product.get("long_description", "")) <= 4000
    checks["attributes"] = bool(product.get("attributes", {}))

    base_passed = sum(bool(v) for v in checks.values())
    base_total = len(checks)

    consistency = consistency_validate(product, manufacturer_df, lov_df)
    checks.update({f"consistency_{k}": v for k, v in consistency["checks"].items()})

    passed = sum(bool(v) for v in checks.values())
    total = len(checks)
    score = round((passed / total) * 100, 2) if total else 0

    # High-risk consistency issues always require human review.
    needs_review = score < 90 or consistency["high_risk_count"] > 0 or consistency["medium_risk_count"] > 0

    product["validation"] = {
        "checks": checks,
        "passed": passed,
        "total": total,
        "status": "PASS" if not consistency["issues"] and passed == total else "REVIEW",
        "consistency": consistency,
    }
    product["quality_score"] = score
    product["needs_human_review"] = needs_review

    return product
