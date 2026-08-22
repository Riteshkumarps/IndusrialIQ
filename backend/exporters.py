from pathlib import Path
import json
import pandas as pd


def flatten_product(product):
    row = {
        "ID": product.get("id"),
        "MPN": product.get("mpn"),
        "Manufacturer": product.get("manufacturer"),
        "Brand": product.get("brand"),
        "Category": product.get("category"),
        "Product Type": product.get("product_type"),
        "Product Title": product.get("title"),
        "Invoice Description": product.get("invoice_description"),
        "Mobile Description": product.get("mobile_description"),
        "Short Description": product.get("short_description"),
        "Long Description": product.get("long_description"),
        "Quality Score": product.get("quality_score"),
        "Needs Human Review": product.get("needs_human_review"),
        "Validation Status": product.get("validation", {}).get("status"),
    }

    for name, obj in product.get("attributes", {}).items():
        row[f"ATTRIBUTE_{name}_VALUE"] = obj.get("value")
        row[f"ATTRIBUTE_{name}_UOM"] = obj.get("uom")
        row[f"ATTRIBUTE_{name}_CONFIDENCE"] = obj.get("confidence")

    return row


def export_excel(products, output_path: Path):
    rows = [flatten_product(p) for p in products]
    pd.DataFrame(rows).to_excel(output_path, index=False)
    return output_path


def export_json(products, output_path: Path):
    output_path.write_text(
        json.dumps(products, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path
