# Invoice AI: Step-by-Step Roadmap

**Goal:** turn messy invoice PDFs into clean, checked data in MySQL.

**How to use this file**

1. Unzip the project and open the folder in VS Code (`File > Open Folder`).
2. Do the steps in order. Do not jump ahead.
3. Do not only copy the code. Read each file, change one small thing, and watch a test fail. That is how you learn it.
4. After each step: run the tests, then commit to Git.

```
git add .
```

```
git commit -m "Finish step N"
```

---

## The big idea (keep this in your head)

| Part | Who does it | Why |
|---|---|---|
| Read the text from the PDF | Code | Reliable |
| Find the fields (supplier, date, lines, totals) | **LLM** | Messy text needs language understanding |
| Clean the values (dates, amounts) | Code | Same input, same output |
| Check the rules (totals add up, VAT, dates) | Code | The LLM must never decide what is valid |
| Fix mistakes | LLM, guided by the errors from the code | Retry loop, max 2 times |
| Save | Code, in one transaction | Database rules are the last safety net |

**The LLM is told to copy what the document says, never to fix numbers.** If an invoice is really wrong, the checks catch it and it goes to a person.

## What is in the folder

```
invoice-ai/
  ROADMAP.md            <- this file
  requirements.txt
  .env.example          <- copy to .env
  db/schema.sql         <- the MySQL tables
  generator/            <- makes fake invoices + the correct answers
  tools/                <- plain Python: models, cleaning, validation, pdf text, MySQL loader
  agent/                <- the LLM part: client + extractor + repair prompt
  pipeline.py           <- connects everything, with the retry loop
  eval/                 <- measures accuracy against the correct answers
  app.py                <- Streamlit web app
  tests/                <- pytest tests (no internet and no cost)
```

---

## Step 0: Setup

You need Python 3.10 or newer and MySQL 8.0.16 or newer (older MySQL ignores `CHECK` rules).

Make a virtual environment:

```
python -m venv .venv
```

Activate it on Windows:

```
.venv\Scripts\activate
```

Activate it on Mac or Linux:

```
source .venv/bin/activate
```

Install the packages:

```
pip install -r requirements.txt
```

Copy the settings file, then open `.env` and fill in your API key and database password:

```
cp .env.example .env
```

On Windows PowerShell use `copy .env.example .env`.

**Done when:** this command works and prints a version number.

```
pytest --version
```

---

## Step 1: Fake invoices (and the correct answers)

**Files to read:** `generator/make_invoices.py`

Why fake data? You know the right answers, so you can measure accuracy. And there is no real company data, so nothing private.

```
python -m generator.make_invoices --count 50 --seed 42
```

**Done when:** `data/invoices/` has 50 PDFs and `data/truth/` has 50 JSON files. Open one PDF and one JSON and compare them. About 15 percent of the invoices have a deliberate error (for example a wrong total). That is on purpose.

---

## Step 2: Models and cleaning

**Files to read:** `tools/models.py`, `tools/cleaning.py`, `tests/test_cleaning.py`

Messy values come in (`"1 234,50 kr"`, `"5 nov 2026"`), clean values go out (`Decimal("1234.50")`, `date(2026, 11, 5)`).

```
pytest tests/test_cleaning.py
```

**Try this:** add your own test case, for example an amount format you have seen at work. Make it fail, then fix the code.

**Done when:** all cleaning tests are green.

---

## Step 3: The database schema

**Files to read:** `db/schema.sql`

Create the tables (Linux/Mac, adjust the user if needed):

```
mysql -u root -p < db/schema.sql
```

In VS Code you can also open `db/schema.sql` and run it with your MySQL extension.

Then:

1. Draw the ER diagram of the 4 tables for your README.
2. **Run DataGuardian on `db/schema.sql`.** Your own tool should review your design. Fix what it finds, or write down why you disagree.

**Done when:** the tables exist and DataGuardian has reviewed the schema.

---

## Step 4: Validation rules

**Files to read:** `tools/validation.py`, `tests/test_validation.py`

These are the deterministic rules: line totals, sum of lines, VAT, VAT rate, dates, currency, Swedish org number (Luhn check), duplicates.

```
pytest tests/test_validation.py
```

**Try this:** add a new rule (for example "invoice total must not be negative") and write its test first.

**Done when:** all validation tests are green.

---

## Step 5: The LLM client and extractor

**Files to read:** `agent/llm.py`, `agent/extractor.py`, `tests/test_pipeline.py`

All model calls go through one small method, `complete(system, user)`. To change provider, change `LLM_PROVIDER` in `.env`. A `FakeClient` returns prepared answers, so tests cost nothing.

```
pytest tests/test_pipeline.py
```

Now try the real model on 3 invoices (this uses your API key and costs a little):

```
python -m pipeline data/invoices --limit 3
```

**Want data to stay on your computer?** Install Ollama, start a local model, and in `.env` set `OPENAI_BASE_URL=http://localhost:11434/v1` and `OPENAI_MODEL` to your local model name. Small local models are less accurate, and your evaluation will show how much.

**Done when:** you see `valid`, `repaired` or `needs_review` for each of the 3 invoices.

---

## Step 6: The retry loop

**Files to read:** `pipeline.py` (the function `process_text`)

Flow: extract, clean, validate. If there are problems, send them back to the model (maximum 2 retries). If it still fails, mark the invoice `needs_review`. Duplicate invoices are never retried.

**Try this:** set `max_retries=0` in a test and see what changes. Why is it good to have a limit?

**Done when:** you can explain this loop in your own words, without looking at the code.

---

## Step 7: Save to MySQL

**Files to read:** `tools/loader.py`

Valid invoices go to `suppliers`, `invoices` and `invoice_lines` in one transaction. The rest goes to `needs_review`.

```
python -m pipeline data/invoices --save-db
```

Check the result in MySQL, one query at a time:

```sql
SELECT COUNT(*) FROM invoices;
```

```sql
SELECT s.name, COUNT(*) AS invoices, SUM(i.total_incl_vat) AS total
FROM invoices i JOIN suppliers s ON s.supplier_id = i.supplier_id
GROUP BY s.name ORDER BY total DESC;
```

```sql
SELECT source_file, issues FROM needs_review;
```

**Done when:** the numbers in MySQL match what the pipeline printed.

> The loader and schema were checked for syntax but not run against a live MySQL server when this project was written. If something fails here, that is a normal bug to fix. Read the error message, it usually names the problem.

---

## Step 8: Measure it (the most important step for your CV)

**Files to read:** `eval/evaluate.py`, `eval/oracle.py`

First a free test with a perfect pretend model. This proves the measuring code works:

```
python -m eval.evaluate --provider oracle
```

Then the real model:

```
python -m eval.evaluate
```

It prints a table and saves `eval/results.md`. Paste that table into your README. **Write only the numbers you really measured.**

Things to look for:

- Did the model "fix" invoices that were deliberately wrong? Then field accuracy drops. That is a real finding.
- How many model calls per invoice does it use?
- Compare two models, or a local model and a cloud model, in one table.

**Done when:** your README has a results table from a real run.

---

## Step 9: The web app

**Files to read:** `app.py`

```
streamlit run app.py
```

Upload some PDFs from `data/invoices`, press Process, and look at the results and the issues.

**Done when:** you can show a 1-minute demo. Record it as a short GIF or video for the README.

---

## Step 10: Make it look professional

1. Tests run on every push: the file `.github/workflows/tests.yml` is already there. Push to GitHub and check the green tick.
2. Write a short README: what it does, a diagram of the flow, how to run it, and your results table.
3. Add a "Limits" section. Be honest:
   - Only PDFs with real text (no scans, no OCR yet)
   - Amount `1,234` is read as 1234 (three digits after one separator means thousands)
   - Dates like `05/11/2026` are read day first
   - Swedish VAT rates only

---

## Later upgrades (not now)

These match the "agent cluster" ideas from your lecture. Add them only when the simple version works.

| Idea from the slide | How it fits here |
|---|---|
| Specialist agents | A second document type (contracts) gets its own extractor, and a small router picks which one to use |
| Distributed load | A job queue with workers that process many PDFs in parallel |
| Resilience | Workers retry failed jobs; a failed model call does not stop the batch |
| Isolated agent for sensitive data | The security upgrade: find and mask personal data before anything reaches a model |
| Real-time ETL to a star model | Watch a folder for new PDFs; load a star schema (fact table for invoice lines, dimensions for supplier and date) |
| OCR | Read scanned invoices before the text step |

## CV line (fill in with your real numbers)

> Built a Python pipeline that extracts invoice data with an LLM, validates it with deterministic rules, repairs errors with a guarded retry loop, and loads clean data into MySQL. Measured on N fake invoices: X% field accuracy, Y of Z deliberate errors caught.

---

## If something goes wrong

- **`ModuleNotFoundError: tools`**: run commands from the project root folder, and use `python -m ...` as shown.
- **`KeyError: OPENAI_MODEL`**: your `.env` is missing or incomplete.
- **MySQL access denied**: check `DB_USER` and `DB_PASSWORD` in `.env`.
- **Model returns text instead of JSON**: the retry loop handles it, but if it happens often, try a stronger model.
