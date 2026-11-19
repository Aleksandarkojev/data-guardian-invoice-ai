"""Simple web app:  streamlit run app.py

Upload invoice PDFs, see what the pipeline extracted, and (optionally) save to MySQL.
"""
import io
import json

import pandas as pd
import streamlit as st

from agent.llm import get_client
from pipeline import process_text
from tools.pdf_text import pdf_to_text

st.set_page_config(page_title="Invoice AI", layout="wide")
st.title("Invoice AI")
st.caption("Messy invoices in, clean checked data out.")

provider = st.sidebar.selectbox("Model provider", ["openai", "anthropic"])
max_retries = st.sidebar.slider("Max retries per invoice", 0, 3, 2)
save_to_db = st.sidebar.checkbox("Save results to MySQL")

files = st.file_uploader("Upload invoice PDFs", type="pdf", accept_multiple_files=True)

if files and st.button("Process"):
    client = get_client(provider)
    conn = None
    if save_to_db:
        from tools.loader import DuplicateInvoice, get_connection, load_invoice, save_for_review
        conn = get_connection()

    seen: set = set()
    rows, details = [], []
    progress = st.progress(0.0)
    for number, uploaded in enumerate(files, start=1):
        text = pdf_to_text(io.BytesIO(uploaded.read()))
        result = process_text(text, client, source_file=uploaded.name, max_retries=max_retries, seen=seen)

        if conn is not None:
            if result.status != "needs_review" and result.invoice is not None:
                try:
                    load_invoice(conn, result.invoice, source_file=uploaded.name)
                except DuplicateInvoice:
                    result.status = "needs_review"
            else:
                save_for_review(conn, uploaded.name, result.raw, result.issues)

        invoice = result.invoice
        rows.append({
            "file": uploaded.name,
            "status": result.status,
            "attempts": result.attempts,
            "supplier": invoice.supplier_name if invoice else None,
            "invoice_number": invoice.invoice_number if invoice else None,
            "total_incl_vat": str(invoice.total_incl_vat) if invoice else None,
            "issues": ", ".join(issue.code for issue in result.issues),
        })
        details.append((uploaded.name, result))
        progress.progress(number / len(files))

    table = pd.DataFrame(rows)
    st.subheader("Results")
    st.dataframe(table, use_container_width=True)
    st.download_button("Download results (CSV)", table.to_csv(index=False), "results.csv", "text/csv")

    st.subheader("Details")
    for name, result in details:
        with st.expander(f"{name}: {result.status}"):
            for issue in result.issues:
                st.warning(f"{issue.code}: {issue.message}")
            if result.invoice is not None:
                st.json(json.loads(result.invoice.model_dump_json()))
