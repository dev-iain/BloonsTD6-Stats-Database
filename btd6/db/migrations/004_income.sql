ALTER TABLE bloons ADD COLUMN pop_cash INTEGER CHECK (pop_cash IS NULL OR pop_cash >= 0);
ALTER TABLE bloons ADD COLUMN pop_cash_super INTEGER CHECK (pop_cash_super IS NULL OR pop_cash_super >= 0);

CREATE TABLE income_thresholds (
    max_round INTEGER PRIMARY KEY CHECK (max_round >= 1),
    multiplier REAL NOT NULL CHECK (multiplier >= 0)
);

CREATE TABLE income_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    final_multiplier REAL NOT NULL CHECK (final_multiplier >= 0)
);
