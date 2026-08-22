import React, { useEffect, useMemo, useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

function Stat({ label, value }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function App() {
  const [products, setProducts] = useState([]);
  const [selected, setSelected] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState({ brand: "", category: "" });

  async function loadProducts() {
    const res = await fetch(`${API}/api/products`);
    const data = await res.json();
    setProducts(data.products || []);
    if (!selected && data.products?.length) {
      setSelected(data.products[0]);
    }
  }

  useEffect(() => {
    loadProducts();
  }, []);

  const stats = useMemo(() => {
    const review = products.filter((p) => p.needs_human_review).length;
    const scores = products.map((p) => Number(p.quality_score || 0));
    const avg = scores.length
      ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)
      : "0";

    return {
      total: products.length,
      review,
      approved: products.length - review,
      avg,
    };
  }, [products]);

  async function uploadFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setMessage("Processing products...");

    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch(`${API}/api/process-file`, {
        method: "POST",
        body: form,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Upload failed");
      }

      setMessage(`${data.processed} products processed.`);
      await loadProducts();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  async function review(action, edits = {}) {
    if (!selected) return;

    if (action === "edit" && !editing) {
      setEditValues({
        brand: selected.brand || "",
        category: selected.category || "",
      });
      setEditing(true);
      return;
    }

    try {
      setMessage(`${action === "edit" ? "Editing" : action === "approve" ? "Approving" : "Rejecting"} product...`);

      const res = await fetch(`${API}/api/review/${selected.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, edits }),
      });

      const data = await res.json();

      if (!res.ok) {
        const detail = typeof data.detail === "object" ? data.detail : { message: data.detail };
        const issueText = (detail.issues || [])
          .map((i) => i.message)
          .join(" | ");
        throw new Error(`${detail.message || "Action failed"}${issueText ? ` ${issueText}` : ""}`);
      }

      setSelected(data);
      setEditing(false);
      await loadProducts();
      setMessage(
        action === "approve"
          ? "✅ Product approved successfully."
          : action === "reject"
            ? "❌ Product rejected and retained for audit."
            : "✏️ Product edited and revalidated."
      );
    } catch (error) {
      console.error(error);
      setMessage(`⚠️ ${error.message}`);
    }
  }


  return (
    <div className="app">
      <header>
        <div>
          <div className="eyebrow">AI PRODUCT INTELLIGENCE</div>
          <h1>IndustrialIQ</h1>
          <p>
            Clean → Understand → Enrich → Validate → Review
          </p>
        </div>

        <label className="upload">
          {uploading ? "Processing..." : "Upload Catalog"}
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={uploadFile}
            disabled={uploading}
          />
        </label>
      </header>

      {message && <div className="message">{message}</div>}

      <section className="stats">
        <Stat label="Products" value={stats.total} />
        <Stat label="Auto-approved" value={stats.approved} />
        <Stat label="Human review" value={stats.review} />
        <Stat label="Avg. quality" value={`${stats.avg}%`} />
      </section>

      <main className="grid">
        <section className="panel">
          <div className="panel-head">
            <h2>Products</h2>
            <span>{products.length}</span>
          </div>

          <div className="product-list">
            {products.map((product) => (
              <button
                className={`product-row ${
                  selected?.id === product.id ? "selected" : ""
                }`}
                key={product.id}
                onClick={() => setSelected(product)}
              >
                <div>
                  <strong>{product.mpn || "No MPN"}</strong>
                  <small>{product.title || product.raw_description}</small>
                </div>

                <div className="row-right">
                  <b>{Number(product.quality_score || 0).toFixed(0)}%</b>
                  {product.needs_human_review && (
                    <span className="review-pill">Review</span>
                  )}
                </div>
              </button>
            ))}

            {!products.length && (
              <div className="empty">
                Upload the sample CSV to start the demo.
              </div>
            )}
          </div>
        </section>

        <section className="panel detail">
          {!selected ? (
            <div className="empty">
              Select a product to inspect the AI output.
            </div>
          ) : (
            <>
              <div className="detail-head">
                <div>
                  <div className="eyebrow">PRODUCT RECORD</div>
                  <h2>{selected.mpn}</h2>
                  <p>{selected.raw_description}</p>
                </div>
                <div className="score">
                  {Number(selected.quality_score || 0).toFixed(0)}%
                  <small>Quality</small>
                </div>
              </div>

              <div className="facts">
                <div><span>Manufacturer</span><strong>{selected.manufacturer || "—"}</strong></div>
                <div>
                  <span>Brand</span>
                  {editing ? (
                    <input
                      value={editValues.brand}
                      onChange={(event) => setEditValues({ ...editValues, brand: event.target.value })}
                    />
                  ) : <strong>{selected.brand || "—"}</strong>}
                </div>
                <div>
                  <span>Category</span>
                  {editing ? (
                    <input
                      value={editValues.category}
                      onChange={(event) => setEditValues({ ...editValues, category: event.target.value })}
                    />
                  ) : <strong>{selected.category || "—"}</strong>}
                </div>
                <div><span>Product Type</span><strong>{selected.product_type || "—"}</strong></div>
              </div>

              <h3>Attributes</h3>
              <div className="attributes">
                {Object.entries(selected.attributes || {}).map(([key, obj]) => (
                  <div className="attribute" key={key}>
                    <div>
                      <span>{key.replaceAll("_", " ")}</span>
                      <strong>
                        {obj.value || "—"} {obj.uom || ""}
                      </strong>
                    </div>
                    <small>{Math.round((obj.confidence || 0) * 100)}%</small>
                  </div>
                ))}
              </div>

              <h3>Generated Content</h3>
              <div className="content-box">
                <label>Title</label>
                <p>{selected.title}</p>

                <label>Invoice</label>
                <p>{selected.invoice_description}</p>

                <label>Mobile</label>
                <p>{selected.mobile_description}</p>

                <label>Short</label>
                <p>{selected.short_description}</p>

                <label>Long</label>
                <p>{selected.long_description}</p>
              </div>

              <h3>Validation</h3>
              <div className="checks">
                {Object.entries(selected.validation?.checks || {}).map(
                  ([name, value]) => (
                    <div className={value ? "pass" : "fail"} key={name}>
                      <span>{value ? "✓" : "!"}</span>
                      {name.replaceAll("_", " ")}
                    </div>
                  )
                )}
              </div>

              <h3>Consistency Guardrails</h3>
              <div className="consistency-summary">
                <div className={`consistency-status ${selected.validation?.consistency?.issues?.length ? "warning" : "ok"}`}>
                  {selected.validation?.consistency?.issues?.length
                    ? `${selected.validation.consistency.issues.length} issue(s) require review`
                    : "✓ Cross-field consistency passed"}
                </div>
                {(selected.validation?.consistency?.issues || []).map((issue, index) => (
                  <div className="consistency-issue" key={`${issue.code}-${index}`}>
                    <strong>{issue.severity?.toUpperCase()} · {issue.code}</strong>
                    <p>{issue.message}</p>
                  </div>
                ))}
              </div>

              <h3>Evidence</h3>
              <div className="evidence">
                {(selected.evidence || []).map((item, index) => (
                  <div key={index}>
                    <strong>{item.source}</strong>
                    <p>{item.snippet}</p>
                  </div>
                ))}
              </div>

              <div className="actions">
                {editing ? (
                  <>
                    <button className="primary" onClick={() => review("edit", editValues)}>
                      Save edit
                    </button>
                    <button onClick={() => setEditing(false)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button className="primary" onClick={() => review("approve")}>
                      Approve
                    </button>
                    <button onClick={() => review("edit")}>Edit</button>
                    <button className="danger" onClick={() => review("reject")}>
                      Reject
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </section>
      </main>

      <footer>
        <a href={`${API}/api/export`} target="_blank" rel="noreferrer">
          Export enriched Excel
        </a>
        <a href={`${API}/docs`} target="_blank" rel="noreferrer">
          API documentation
        </a>
      </footer>
    </div>
  );
}

export default App;
