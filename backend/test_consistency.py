import pandas as pd
from pipeline import process_dataframe, load_reference_data
from validators import validate_product


def main():
    df = pd.read_csv("../sample/sample_input.csv")
    refs = load_reference_data()
    products = process_dataframe(df)
    target = next(p for p in products if p["mpn"] == "DW088CG")

    assert target["brand"] == "DEWALT®"
    assert target["category"] == "Line Lasers"
    assert not target["validation"]["consistency"]["issues"]

    target["brand"] = "Milwaukee®"
    target["category"] = "Cut-Off Discs"
    validate_product(
        target,
        refs["manufacturers"],
        refs["brands"],
        refs["categories"],
        manufacturer_df=refs["manufacturer_df"],
        lov_df=refs["lov_df"],
    )

    codes = {issue["code"] for issue in target["validation"]["consistency"]["issues"]}
    assert "BRAND_MANUFACTURER_MISMATCH" in codes
    assert "CATEGORY_DESCRIPTION_MISMATCH" in codes
    assert target["needs_human_review"] is True
    print("Consistency guardrail test: PASS")


if __name__ == "__main__":
    main()
