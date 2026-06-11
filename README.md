# Pâtisserie AI — Chef Instructor Intelligence System

A RAG-powered assistant for pastry academy instructors. Upload any recipe PDF
and ask questions, scale yields, build indent sheets, and check ingredient ratios.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · LangChain · LangGraph |
| Vector DB | Pinecone |
| LLM + Embeddings | Nebius Token Factory (OpenAI-compatible) |
| Reranking | Cohere free tier |
| PDF parsing | pdfplumber |
| Keyword search | BM25 (rank-bm25) |
| Frontend | React · Vite · Tailwind CSS |

---

## Setup

### 1. Environment variables

```bash
cp .env.example .env
# Fill in: NEBIUS_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME, PINECONE_NAMESPACE
```

### 2. Pinecone index

Create a Pinecone index with:
- **Dimensions**: `4096` (matches `BAAI/bge-en-icl`)
- **Metric**: `cosine`
- **Name**: whatever you set in `PINECONE_INDEX_NAME`

### 3. Install backend dependencies

Requires **Python 3.12** (3.14 is not yet supported by pydantic-core).
On macOS: `brew install python@3.12`

```bash
cd backend
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
```

---

## Running

### Start the backend

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Start the frontend

```bash
cd frontend
npm run dev
# Open http://localhost:5173
```

---

## Upload a PDF

### Via the UI

Drag and drop any recipe PDF onto the sidebar upload zone. The system parses,
embeds, and indexes it automatically. Idempotent — re-uploading the same PDF
updates existing vectors without duplicating them.

### Via curl

```bash
curl -X POST http://localhost:8000/ingest/upload \
  -F "file=@/path/to/your/recipe.pdf"
```

Response:
```json
{
  "file": "recipe.pdf",
  "chunks": 42,
  "recipes": 12,
  "status": "ok"
}
```

PDFs that don't follow the academy table format (notes, articles, other handouts)
are still fully ingested via page-level fallback chunking and remain searchable.

---

## What the agent can do

| Intent | Example query |
|---|---|
| Find recipes | "Show me all recipes that use gelatine" |
| Scale a yield | "Scale the croissant dough to 5000g" |
| Build an indent sheet | "Build an indent sheet for croissants and soft rolls" |
| Check for anomalies | "Check the dark chocolate tart for ratio errors" |
| General knowledge | "Why does lamination butter need the same consistency as the dough?" |

---

## Run evaluation

The evaluation script tests 15 queries against a running backend:

```bash
cd backend
.venv/bin/python -m scripts.evaluate
# Or write a JSON report:
.venv/bin/python -m scripts.evaluate --out report.json
# Run specific tests only:
.venv/bin/python -m scripts.evaluate --ids FR-01 AC-01 SR-01
```

---

## Notes on non-linear scaling

When scaling yeast, gelatin, baking powder, baking soda, or salt, the system
applies a dampening factor and shows a ⚠ warning. The instructor should always
verify these quantities before production — the dampened values are starting
points, not definitive figures.

## Notes on anomaly checking

The threshold database (`data/thresholds.json`) currently covers:
- **Gelatin** — 0.5–3.0% of liquid weight
- **Dark chocolate in ganache** — 100–250% of cream weight

Additional rules can be added directly to `data/thresholds.json` using the
same schema.
