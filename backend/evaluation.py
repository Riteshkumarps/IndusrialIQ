import pandas as pd
from pipeline import normalize_input_columns


def normalize_value(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def evaluate(predicted_products, expected_df):
    """
    Flexible evaluator for the MVP.

    It compares fields that exist in both predicted output and expected
    ground truth. For the actual hackathon workbook, extend FIELD_MAP
    after inspecting the exact Delivery Format headers.
    """
    expected = normalize_input_columns(expected_df)

    expected_by_mpn = {}
    if "mpn" in expected.columns:
        for _, row in expected.iterrows():
            expected_by_mpn[normalize_value(row.get("mpn"))] = row.to_dict()

    field_map = {
        "manufacturer": ["Manufacturer", "MANUFACTURER_NAME", "Part_Manuf"],
        "brand": ["Brand", "BRAND_NAME"],
        "category": ["Category", "Fine", "Leaf Node"],
        "title": ["Product Title", "PRODUCT_TITLE", "Title"],
        "short_description": ["Short Description", "SHORT_DESCRIPTION"],
        "long_description": ["Long Description", "LONG_DESCRIPTION"],
    }

    results = []
    total = 0
    correct = 0

    for product in predicted_products:
        key = normalize_value(product.get("mpn"))
        truth = expected_by_mpn.get(key)

        if not truth:
            continue

        for predicted_field, expected_fields in field_map.items():
            expected_col = next(
                (c for c in expected_fields if c in truth),
                None
            )

            if not expected_col:
                continue

            p = normalize_value(product.get(predicted_field))
            e = normalize_value(truth.get(expected_col))

            if not e:
                continue

            total += 1
            ok = p == e
            correct += int(ok)

            results.append({
                "mpn": product.get("mpn"),
                "field": predicted_field,
                "predicted": product.get(predicted_field),
                "expected": truth.get(expected_col),
                "correct": ok,
            })

    accuracy = round(correct / total * 100, 2) if total else 0

    return {
        "accuracy": accuracy,
        "correct": correct,
        "compared": total,
        "details": results,
    }
