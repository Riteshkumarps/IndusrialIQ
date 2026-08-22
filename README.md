# INDUSTRIALIQ — AI Product Intelligence MVP

A hackathon-ready MVP for the UniHack / industrial product intelligence challenge.

## What this project does

Raw industrial product data:

`MPN + Part Description + Brand + Manufacturer`

is transformed into:

- cleaned product data
- manufacturer / brand resolution
- category classification
- attribute extraction
- unit normalization
- source/evidence records
- product title and descriptions
- validation
- confidence score
- human-review flag
- JSON + Excel export
- ground-truth evaluation

The architecture follows the challenge materials: AI is used for understanding and extraction, while controlled vocabularies, UOM rules and deterministic validation constrain the final output.

## Stack

- Backend: Python + FastAPI
- Data: Pandas + OpenPyXL
- Entity resolution: RapidFuzz
- Lightweight local RAG: TF-IDF + cosine similarity
- Optional LLM: any OpenAI-compatible `/chat/completions` endpoint
- Frontend: React + Vite
- Storage: local JSON files for MVP

React is used as a component-based UI, and FastAPI handles multipart file uploads. See the official docs:
- https://react.dev/
- https://fastapi.tiangolo.com/tutorial/request-files/

## Project structure

```text
industrialiq/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── pipeline.py
│   ├── llm.py
│   ├── rag.py
│   ├── validators.py
│   ├── exporters.py
│   ├── evaluation.py
│   ├── requirements.txt
│   ├── data/
│   │   ├── manufacturer_brand.csv
│   │   ├── lov.csv
│   │   ├── uom.csv
│   │   └── fraction.csv
│   └── documents/
│
├── frontend/
│   ├── package.json
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       └── styles.css
│
└── sample/
    └── sample_input.csv
```

## 1. Backend setup

Python 3.10+ recommended.

```bash
cd backend
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install:

```bash
pip install -r requirements.txt
```

Run:

```bash
uvicorn main:app --reload --port 8000
```

API:

`http://localhost:8000`

Swagger:

`http://localhost:8000/docs`

## 2. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal.

## 3. Optional LLM

The application works without an API key using deterministic/local extraction.

For richer AI generation, create environment variables:

```text
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=YOUR_KEY
LLM_MODEL=YOUR_MODEL
```

The code intentionally uses a small HTTP adapter instead of tying the project to one vendor SDK.

## 4. Add challenge reference files

Copy the challenge reference data into:

```text
backend/data/
```

Recommended mappings:

```text
manufacturer_brand.csv
lov.csv
uom.csv
fraction.csv
```

If your supplied files are Excel workbooks, convert them to CSV or change `load_reference_data()` in `backend/pipeline.py` to read the required sheets directly.

Put manufacturer PDFs/specifications in:

```text
backend/documents/
```

## 5. API endpoints

### Health

```http
GET /api/health
```

### Process one product

```http
POST /api/process
Content-Type: application/json
```

### Upload CSV/XLSX

```http
POST /api/process-file
Content-Type: multipart/form-data
```

### Export current results

```http
GET /api/export
```

### Review a product

```http
POST /api/review/{product_id}
```

### Evaluation

```http
POST /api/evaluate
```

## 6. Important production/hackathon principle

Do NOT let the LLM invent technical values.

The pipeline is:

```text
Raw data
  ↓
Cleaning
  ↓
Entity resolution
  ↓
Classification
  ↓
Attribute extraction
  ↓
Source/RAG evidence
  ↓
Normalization
  ↓
Description generation
  ↓
Deterministic validation
  ↓
Confidence
  ↓
Auto-approve OR Human review
```

## 7. Demo flow

1. Upload `sample/sample_input.csv`.
2. Open the product list.
3. Click a product.
4. Show extracted attributes.
5. Show evidence/source.
6. Show validation checks.
7. Show confidence.
8. Show generated descriptions.
9. Export Excel.
10. Run evaluation against the 200-item ground truth.

## 8. Scaling

For the hackathon:

- prove the pipeline on the 200 known-good rows
- measure field-level accuracy
- then process the 1,000-row input
- add asynchronous jobs / queues if processing becomes slow
- replace local JSON with MongoDB/PostgreSQL for production
- replace TF-IDF with embeddings/vector DB if needed

## Consistency Guardrails

The updated build adds a deterministic cross-field validation layer after AI extraction and after every human edit.

It checks:

- Manufacturer ↔ Brand relationship against `manufacturer_brand.csv`
- Category ↔ source-description consistency
- Product Type ↔ Category consistency for common industrial classes
- Attribute ↔ Category applicability against `lov.csv`

A failed high/medium-risk consistency rule sends the product to human review. The Approve action is blocked until the issues are resolved. The UI displays the exact validation issue and affected fields.

### Demo scenario

For `DW088CG` (`Dewalt Laser - Green Cross Line`), changing the brand to `Milwaukee®` and the category to `Cut-Off Discs` will produce two high-risk validation issues:

1. Brand/manufacturer mismatch
2. Category/description mismatch

The product cannot be approved while those issues exist.
