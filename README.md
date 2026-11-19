# Invoice AI

Turns messy invoice PDFs into clean, checked data in MySQL.

**Flow:** PDF -> text -> LLM extraction -> cleaning -> validation rules -> repair loop (max 2 retries) -> MySQL

The LLM only reads the document. Deterministic code decides what is valid.
Invoices that cannot be fixed go to a `needs_review` table for a human.

## Run it

```
pip install -r requirements.txt
python -m generator.make_invoices --count 50 --seed 42
pytest
python -m eval.evaluate
streamlit run app.py
```

See `ROADMAP.md` for the full step-by-step guide.

## Results

_Paste the table from `eval/results.md` here after you run the evaluation with a real model._

## Limits

- PDFs with real text only (no scans, no OCR yet)
- Swedish VAT rates and Swedish org numbers
- A single separator with exactly three digits after it (`1,234`) is read as thousands
- Dates like `05/11/2026` are read day first

## ER Diagram

![Invoice AI ER Diagram](db/er-diagram.png)