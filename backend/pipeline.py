import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from rapidfuzz import process, fuzz

from config import DATA_DIR, DOCS_DIR
from llm import chat_json, llm_available
from models import Evidence
from rag import LocalRAG, read_documents
from validators import clean_text, normalize_uom, normalize_text_units, validate_product, build_manufacturer_brand_map, _norm


COLUMN_ALIASES = {
    "mpn": ["Mfg_Part_Num", "MPN", "Part Number", "Manufacturer Part Number"],
    "description": ["Part_Desc", "Part Desc", "Description", "Product Description"],
    "e1_brand": ["E1_Brand", "E1 Brand"],
    "unilog_brand": ["Unilog_Brand", "Unilog Brand"],
    "dib_brand": ["DIB_Brand", "DIB Brand"],
    "manufacturer": ["Part_Manuf", "Part Manuf", "Manufacturer", "Manufacturer Name"],
}


def find_column(df, aliases):
    normalized = {str(c).strip().lower(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in normalized:
            return normalized[alias.lower()]
    return None


def normalize_input_columns(df):
    mapping = {}
    for target, aliases in COLUMN_ALIASES.items():
        col = find_column(df, aliases)
        if col:
            mapping[col] = target

    return df.rename(columns=mapping).copy()


def load_table(filename: str) -> pd.DataFrame:
    path = DATA_DIR / filename

    if not path.exists():
        return pd.DataFrame()

    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def load_reference_data():
    manufacturer_df = load_table("manufacturer_brand.csv")
    lov_df = load_table("lov.csv")
    uom_df = load_table("uom.csv")

    manufacturers = []
    brands = []
    categories = []

    if not manufacturer_df.empty:
        for col in ["MANUFACTURER_NAME", "Manufacturer", "manufacturer"]:
            if col in manufacturer_df.columns:
                manufacturers = (
                    manufacturer_df[col]
                    .dropna()
                    .astype(str)
                    .drop_duplicates()
                    .tolist()
                )
                break

        for col in ["BRAND_NAME", "Brand", "brand"]:
            if col in manufacturer_df.columns:
                brands = (
                    manufacturer_df[col]
                    .dropna()
                    .astype(str)
                    .drop_duplicates()
                    .tolist()
                )
                break

    if not lov_df.empty:
        for col in ["Classpath", "ClassPath", "Category", "Leaf Node", "Fine"]:
            if col in lov_df.columns:
                categories = (
                    lov_df[col]
                    .dropna()
                    .astype(str)
                    .drop_duplicates()
                    .tolist()
                )
                break

    uoms = []
    if not uom_df.empty:
        for col in ["UOM", "Approved UOM", "Abbreviation", "UNIT"]:
            if col in uom_df.columns:
                uoms = (
                    uom_df[col]
                    .dropna()
                    .astype(str)
                    .drop_duplicates()
                    .tolist()
                )
                break

    return {
        "manufacturer_df": manufacturer_df,
        "lov_df": lov_df,
        "uom_df": uom_df,
        "manufacturers": manufacturers,
        "brands": brands,
        "categories": categories,
        "uoms": uoms,
    }


def best_match(value: Optional[str], choices: List[str]) -> Tuple[Optional[str], float]:
    if not value or not choices:
        return None, 0.0

    result = process.extractOne(value, choices, scorer=fuzz.WRatio)
    if not result:
        return None, 0.0

    match, score, _ = result
    return match, round(float(score), 2)


def best_brand_for_manufacturer(brand_value: Optional[str], manufacturer: Optional[str], refs: Dict) -> Tuple[Optional[str], float]:
    """Resolve brand within the manufacturer's allowed brand set when possible."""
    if not brand_value:
        return None, 0.0

    relation = build_manufacturer_brand_map(refs.get("manufacturer_df"))
    allowed = relation.get(_norm(manufacturer or ""))
    if allowed:
        # Recover canonical display values from the master table.
        canonical = []
        df = refs.get("manufacturer_df")
        if df is not None and not df.empty:
            mcol = next((c for c in ["MANUFACTURER_NAME", "Manufacturer", "manufacturer"] if c in df.columns), None)
            bcol = next((c for c in ["BRAND_NAME", "Brand", "brand"] if c in df.columns), None)
            if mcol and bcol:
                for _, row in df.iterrows():
                    if _norm(row.get(mcol)) == _norm(manufacturer) and _norm(row.get(bcol)) in allowed:
                        canonical.append(str(row.get(bcol)))
        return best_match(brand_value, canonical)

    return best_match(brand_value, refs["brands"])


def regex_attributes(text: str) -> Dict[str, Dict]:
    text = text or ""
    attrs = {}

    patterns = [
        ("voltage_rating", r"\b(\d+(?:\.\d+)?)\s*V\b"),
        ("amperage_rating", r"\b(\d+(?:\.\d+)?)\s*A\b"),
        ("sound_level", r"\b(\d+(?:\.\d+)?)\s*dBA\b"),
        ("wash_cycles", r"\b(\d+)[-\s]*(?:wash\s*)?cycles?\b"),
        ("diameter", r'(\d+(?:[-/]\d+)?(?:\.\d+)?)\s*(?:inches|inch|in\.|")'),
    ]

    for label, pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            raw = m.group(1)
            uom = None

            if label == "voltage_rating":
                uom = "V"
            elif label == "amperage_rating":
                uom = "A"
            elif label == "sound_level":
                uom = "dBA"
            elif label == "diameter":
                uom = "in"

            attrs[label] = {
                "value": normalize_uom(f"{raw} {uom}" if uom else raw),
                "uom": uom,
                "confidence": 0.90,
                "evidence": {
                    "source": "raw_input",
                    "snippet": m.group(0),
                    "confidence": 0.90,
                },
            }

    if re.search(r"\bstainless\s+steel\b|\bSST\b|\bSS\b", text, re.I):
        attrs["material"] = {
            "value": "Stainless Steel",
            "uom": None,
            "confidence": 0.80,
            "evidence": {
                "source": "raw_input",
                "snippet": "stainless steel / SS",
                "confidence": 0.80,
            },
        }

    if re.search(r"\bleg\s+mount", text, re.I):
        attrs["mounting_type"] = {
            "value": "Leg",
            "uom": None,
            "confidence": 0.90,
            "evidence": {
                "source": "raw_input",
                "snippet": "Leg Mounting",
                "confidence": 0.90,
            },
        }

    return attrs


def classify_text(description: str, lov_df: pd.DataFrame) -> Dict:
    text = (description or "").lower()

    rules = [
        (["dishwasher", "dish washer"], "Built-In Dishwashers"),
        (["faucet", "faucets"], "Faucets"),
        (["fitting", "coupling", "elbow", "tee"], "Fittings"),
        (["laser", "cross line"], "Line Lasers"),
        (["saw blade"], "Saw Blades"),
        (["router bit"], "Router Bits"),
        (["socket adapter"], "Socket Adapters"),
        (["cut off disc", "cut-off disc"], "Cut-Off Discs"),
    ]

    for keywords, category in rules:
        if any(k in text for k in keywords):
            return {
                "category": category,
                "confidence": 0.85,
            }

    if llm_available():
        prompt = f"""
Return JSON only.
Classify this industrial product into a concise product category.

Description:
{description}

JSON:
{{"category":"...", "product_type":"...", "confidence":0.0}}
"""
        try:
            result = chat_json(
                "You classify industrial products. Never invent technical attributes.",
                prompt,
            )
            return result
        except Exception:
            pass

    return {
        "category": "Unclassified",
        "confidence": 0.20,
    }


def llm_extract(description: str, category: str) -> Dict:
    if not llm_available():
        return {}

    prompt = f"""
Extract only facts explicitly present in the product text.
Return JSON.
Do not guess.

Category: {category}
Product text: {description}

Schema:
{{
  "product_type": "",
  "series": "",
  "attributes": {{
    "attribute_name": {{
      "value": "",
      "uom": "",
      "confidence": 0.0
    }}
  }}
}}
"""
    try:
        return chat_json(
            "You are a conservative industrial product data extraction agent.",
            prompt,
        )
    except Exception:
        return {}


def generate_content(product: Dict) -> Dict:
    brand = product.get("brand") or product.get("manufacturer") or ""
    series = product.get("attributes", {}).get("series", {}).get("value", "")
    mpn = product.get("mpn", "")
    ptype = product.get("product_type") or "Product"

    attr_parts = []
    for name, obj in product.get("attributes", {}).items():
        if name == "series":
            continue
        value = obj.get("value")
        if value not in (None, ""):
            attr_parts.append(f"{name.replace('_', ' ').title()}: {value}")

    attrs = ", ".join(attr_parts[:8])

    title_parts = [x for x in [brand, series, mpn, ptype] if x]
    title = " ".join(title_parts)

    if attrs:
        short = f"{title}, {attrs}."
        long = f"{title}. Key specifications: {attrs}."
    else:
        short = f"{title}."
        long = f"{title}."

    invoice = normalize_text_units(title).upper()[:40]
    mobile = normalize_text_units(title)[:80]

    return {
        "title": title[:200],
        "invoice_description": invoice,
        "mobile_description": mobile,
        "short_description": short[:500],
        "long_description": long[:4000],
    }


def process_product(row: Dict, refs: Dict, rag: LocalRAG) -> Dict:
    mpn = clean_text(row.get("mpn")) or ""
    description = clean_text(row.get("description")) or ""
    manufacturer_raw = clean_text(row.get("manufacturer"))
    brand_raw = (
        clean_text(row.get("unilog_brand"))
        or clean_text(row.get("dib_brand"))
        or clean_text(row.get("e1_brand"))
    )

    product_id = hashlib.md5(
        f"{mpn}|{description}".encode("utf-8")
    ).hexdigest()[:12]

    manufacturer, manufacturer_score = best_match(
        manufacturer_raw,
        refs["manufacturers"],
    )

    brand, brand_score = best_brand_for_manufacturer(
        brand_raw,
        manufacturer,
        refs,
    )

    classification = classify_text(description, refs["lov_df"])
    category = classification.get("category", "Unclassified")

    regex_attrs = regex_attributes(description)
    llm_data = llm_extract(description, category)

    attrs = regex_attrs.copy()

    # LLM attributes are accepted only as candidates. They receive
    # lower confidence unless corroborated by source/LOV logic.
    for key, value in (llm_data.get("attributes") or {}).items():
        if isinstance(value, dict):
            value.setdefault("confidence", 0.60)
            attrs.setdefault(key, value)

    product = {
        "id": product_id,
        "mpn": mpn,
        "raw_description": description,
        "manufacturer_raw": manufacturer_raw,
        "brand_raw": brand_raw,
        "manufacturer": manufacturer,
        "brand": brand,
        "category": category,
        "department": None,
        "product_type": llm_data.get("product_type"),
        "attributes": attrs,
        "evidence": [],
    }

    # Retrieve manufacturer evidence.
    query = " ".join(
        x for x in [manufacturer or manufacturer_raw or "", mpn, description] if x
    )
    retrieved = rag.retrieve(query, top_k=3)

    for item in retrieved:
        product["evidence"].append({
            "source": item["source"],
            "snippet": item["snippet"],
            "confidence": round(min(0.99, 0.50 + item["score"] / 2), 3),
        })

    # If no RAG evidence exists, raw input remains explicit evidence.
    if not retrieved:
        product["evidence"].append({
            "source": "raw_input",
            "snippet": description[:1000],
            "confidence": 0.70,
        })

    content = generate_content(product)
    product.update(content)

    validate_product(
        product,
        refs["manufacturers"],
        refs["brands"],
        refs["categories"],
        manufacturer_df=refs["manufacturer_df"],
        lov_df=refs["lov_df"],
    )

    product["workflow_status"] = (
        "HUMAN_REVIEW" if product["needs_human_review"] else "AUTO_APPROVED"
    )

    # More conservative review rule.
    if manufacturer_score and manufacturer_score < 80:
        product["needs_human_review"] = True

    if brand_score and brand_score < 80:
        product["needs_human_review"] = True

    product["resolution"] = {
        "manufacturer_confidence": manufacturer_score,
        "brand_confidence": brand_score,
        "classification_confidence": classification.get("confidence", 0),
    }

    return product


def process_dataframe(df: pd.DataFrame) -> List[Dict]:
    df = normalize_input_columns(df)
    refs = load_reference_data()

    docs = read_documents(DOCS_DIR)
    rag = LocalRAG(docs)

    records = df.fillna("").to_dict(orient="records")
    return [process_product(row, refs, rag) for row in records]
