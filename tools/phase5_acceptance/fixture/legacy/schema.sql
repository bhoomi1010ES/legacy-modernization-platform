-- Phase 5 Legacy Database Schema Definition
-- Relational financial ledger with primary keys, foreign keys, unique and check constraints.

CREATE TABLE accounts (
    account_id INTEGER PRIMARY KEY,
    account_number VARCHAR(32) NOT NULL UNIQUE,
    holder_name VARCHAR(128) NOT NULL,
    balance NUMERIC(12, 2) NOT NULL CHECK (balance >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE account_transactions (
    transaction_id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    amount NUMERIC(12, 2) NOT NULL,
    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER')),
    resulting_balance NUMERIC(12, 2) NOT NULL CHECK (resulting_balance >= 0),
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_logs (
    log_id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    action VARCHAR(32) NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_transactions_account ON account_transactions(account_id);
CREATE INDEX idx_audit_logs_account ON audit_logs(account_id);
