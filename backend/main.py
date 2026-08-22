import json
import uuid
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import STORE_DIR, OUTPUT_DIR
from evaluation import evaluate
from exporters import export_excel, export_json
from pipeline import process_dataframe, load_reference_data
from validators import validate_product


app = FastAPI(
    title="IndustrialIQ",
    version="1.0.0",
    description="AI-powered industrial product intelligence MVP",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RESULTS_FILE = STORE_DIR / "results.json"


# ============================================================
# RESULT STORAGE
# ============================================================

def load_results():
    if not RESULTS_FILE.exists():
        return []

    try:
        return json.loads(
            RESULTS_FILE.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError):
        return []


def save_results(results):
    STORE_DIR.mkdir(parents=True, exist_ok=True)

    RESULTS_FILE.write_text(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8",
    )


def clear_results():
    """
    Completely remove the current catalog from active storage.
    """
    save_results([])


# ============================================================
# REQUEST MODELS
# ============================================================

class ReviewRequest(BaseModel):
    action: str
    edits: dict = Field(default_factory=dict)


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "IndustrialIQ",
    }


# ============================================================
# PRODUCTS
# ============================================================

@app.get("/api/products")
def products():
    results = load_results()

    return {
        "count": len(results),
        "products": results,
    }


@app.get("/api/products/{product_id}")
def product(product_id: str):

    for item in load_results():
        if item["id"] == product_id:
            return item

    raise HTTPException(
        status_code=404,
        detail="Product not found"
    )


# ============================================================
# CLEAR CURRENT CATALOG
# ============================================================

@app.delete("/api/products")
def clear_catalog():
    """
    Clear the active catalog.

    Useful before uploading a completely new catalog.
    """

    previous_count = len(load_results())

    clear_results()

    return {
        "success": True,
        "message": "Current catalog cleared successfully.",
        "deleted": previous_count,
        "count": 0,
    }


# ============================================================
# SINGLE PRODUCT PROCESSING
# ============================================================

@app.post("/api/process")
def process_single(payload: dict):

    results = load_results()

    products = process_dataframe(
        pd.DataFrame([payload])
    )

    results.extend(products)

    save_results(results)

    return products[0]


# ============================================================
# FILE PROCESSING
# ============================================================

@app.post("/api/process-file")
async def process_file(
    file: UploadFile = File(...)
):

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Missing filename"
        )

    content = await file.read()

    temp = OUTPUT_DIR / (
        f"{uuid.uuid4().hex}_{file.filename}"
    )

    temp.write_bytes(content)

    try:

        # ----------------------------------------------------
        # READ INPUT FILE
        # ----------------------------------------------------

        suffix = Path(file.filename).suffix.lower()

        if suffix == ".csv":

            df = pd.read_csv(temp)

        elif suffix in {".xlsx", ".xls"}:

            df = pd.read_excel(temp)

        else:

            raise HTTPException(
                status_code=400,
                detail="Only CSV/XLS/XLSX supported in MVP",
            )

        # ----------------------------------------------------
        # VALIDATE EMPTY FILE
        # ----------------------------------------------------

        if df.empty:

            raise HTTPException(
                status_code=400,
                detail="Uploaded file contains no products.",
            )

        # ----------------------------------------------------
        # PROCESS NEW CATALOG
        # ----------------------------------------------------

        products = process_dataframe(df)

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # REPLACE OLD CATALOG
        #
        # DO NOT:
        # results.extend(products)
        #
        # ----------------------------------------------------

        save_results(products)

        return {
            "processed": len(products),
            "count": len(products),
            "products": products,
            "message": (
                f"Catalog replaced successfully. "
                f"{len(products)} products loaded."
            ),
        }

    finally:

        temp.unlink(missing_ok=True)


# ============================================================
# HUMAN REVIEW
# ============================================================

@app.post("/api/review/{product_id}")
def review(
    product_id: str,
    request: ReviewRequest
):

    results = load_results()

    found = next(
        (
            item
            for item in results
            if item["id"] == product_id
        ),
        None
    )

    if found is None:

        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    action = (
        request.action or ""
    ).lower().strip()

    if action not in {
        "approve",
        "reject",
        "edit"
    }:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid action. "
                "Use approve, edit or reject."
            ),
        )

    # ========================================================
    # EDIT
    # ========================================================

    if action == "edit":

        allowed_edit_fields = {
            "manufacturer",
            "brand",
            "category",
            "product_type",
            "title",
            "short_description",
            "long_description",
        }

        for key, value in (
            request.edits or {}
        ).items():

            if key in allowed_edit_fields:

                found[key] = (
                    str(value).strip()
                    if value is not None
                    else None
                )

        refs = load_reference_data()

        validate_product(
            found,
            refs["manufacturers"],
            refs["brands"],
            refs["categories"],
            manufacturer_df=refs["manufacturer_df"],
            lov_df=refs["lov_df"],
        )

        found["workflow_status"] = "HUMAN_REVIEW"

        found["validation"]["status"] = (
            "REVIEW"
            if found["validation"]
                ["consistency"]
                ["issues"]
            else "PASS"
        )

    # ========================================================
    # APPROVE
    # ========================================================

    elif action == "approve":

        refs = load_reference_data()

        validate_product(
            found,
            refs["manufacturers"],
            refs["brands"],
            refs["categories"],
            manufacturer_df=refs["manufacturer_df"],
            lov_df=refs["lov_df"],
        )

        consistency = (
            found
            .get("validation", {})
            .get("consistency", {})
        )

        if consistency.get("issues"):

            found["needs_human_review"] = True

            found["workflow_status"] = "HUMAN_REVIEW"

            save_results(results)

            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Product cannot be approved "
                        "until validation issues "
                        "are resolved."
                    ),
                    "issues": consistency.get(
                        "issues",
                        []
                    ),
                },
            )

        found["needs_human_review"] = False

        found["workflow_status"] = "APPROVED"

        found.setdefault(
            "validation",
            {}
        )["status"] = "APPROVED"

    # ========================================================
    # REJECT
    # ========================================================

    elif action == "reject":

        # Keep rejected products for audit.
        found["needs_human_review"] = True

        found["workflow_status"] = "REJECTED"

        found.setdefault(
            "validation",
            {}
        )["status"] = "REJECTED"

    # ========================================================
    # SAVE UPDATED RECORD
    # ========================================================

    save_results(results)

    return found


# ============================================================
# EXCEL EXPORT
# ============================================================

@app.get("/api/export")
def export():

    results = load_results()

    if not results:

        raise HTTPException(
            status_code=404,
            detail="No results available"
        )

    path = (
        OUTPUT_DIR
        / "IndustrialIQ_Enriched_Catalog.xlsx"
    )

    export_excel(
        results,
        path
    )

    return FileResponse(
        path,
        filename=path.name,
        media_type=(
            "application/"
            "vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
    )


# ============================================================
# JSON EXPORT
# ============================================================

@app.get("/api/export-json")
def export_json_endpoint():

    results = load_results()

    if not results:

        raise HTTPException(
            status_code=404,
            detail="No results available"
        )

    path = (
        OUTPUT_DIR
        / "IndustrialIQ_Enriched_Catalog.json"
    )

    export_json(
        results,
        path
    )

    return FileResponse(
        path,
        filename=path.name,
        media_type="application/json",
    )


# ============================================================
# EVALUATION
# ============================================================

@app.post("/api/evaluate")
async def evaluate_endpoint(
    file: UploadFile = File(...)
):

    content = await file.read()

    temp = OUTPUT_DIR / (
        f"eval_{uuid.uuid4().hex}_{file.filename}"
    )

    temp.write_bytes(content)

    try:

        suffix = Path(
            file.filename
        ).suffix.lower()

        if suffix == ".csv":

            expected_df = pd.read_csv(temp)

        elif suffix in {
            ".xlsx",
            ".xls"
        }:

            expected_df = pd.read_excel(temp)

        else:

            raise HTTPException(
                status_code=400,
                detail="Only CSV/XLS/XLSX supported",
            )

        return evaluate(
            load_results(),
            expected_df
        )

    finally:

        temp.unlink(
            missing_ok=True
        )