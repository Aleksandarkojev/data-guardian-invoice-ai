-- Invoice AI: target schema (MySQL 8.0.16 or newer, so CHECK constraints are enforced)
CREATE DATABASE IF NOT EXISTS invoice_ai CHARACTER SET utf8mb4;
USE invoice_ai;

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id  INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    org_number   VARCHAR(20)  NULL,
    UNIQUE KEY uq_suppliers_org_number (org_number),
    KEY idx_suppliers_name (name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id      INT AUTO_INCREMENT PRIMARY KEY,
    supplier_id     INT NOT NULL,
    invoice_number  VARCHAR(50) NOT NULL,
    invoice_date    DATE NOT NULL,
    due_date        DATE NULL,
    currency        CHAR(3) NOT NULL,
    total_excl_vat  DECIMAL(12,2) NOT NULL,
    vat_amount      DECIMAL(12,2) NOT NULL,
    total_incl_vat  DECIMAL(12,2) NOT NULL,
    source_file     VARCHAR(255) NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_invoices_supplier_number (supplier_id, invoice_number),
    KEY idx_invoices_invoice_date (invoice_date),
    CONSTRAINT fk_invoices_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id),
    CONSTRAINT chk_invoices_total CHECK (total_incl_vat = total_excl_vat + vat_amount),
    CONSTRAINT chk_invoices_due CHECK (due_date IS NULL OR due_date >= invoice_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS invoice_lines (
    line_id      INT AUTO_INCREMENT PRIMARY KEY,
    invoice_id   INT NOT NULL,
    line_no      INT NOT NULL,
    description  VARCHAR(500) NOT NULL,
    quantity     DECIMAL(12,3) NOT NULL,
    unit_price   DECIMAL(12,2) NOT NULL,
    line_total   DECIMAL(12,2) NOT NULL,
    UNIQUE KEY uq_invoice_lines_invoice_line (invoice_id, line_no),
    CONSTRAINT fk_invoice_lines_invoice FOREIGN KEY (invoice_id)
        REFERENCES invoices (invoice_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Invoices that could not be fixed automatically wait here for a human.
CREATE TABLE IF NOT EXISTS needs_review (
    review_id    INT AUTO_INCREMENT PRIMARY KEY,
    source_file  VARCHAR(255) NOT NULL,
    raw_json     JSON NULL,
    issues       JSON NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
