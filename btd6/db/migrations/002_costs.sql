ALTER TABLE towers ADD COLUMN base_cost INTEGER CHECK (base_cost IS NULL OR base_cost >= 0);

CREATE TABLE upgrade_costs (
    id INTEGER PRIMARY KEY,
    tower_id INTEGER NOT NULL REFERENCES towers (id) ON DELETE CASCADE,
    path_index INTEGER NOT NULL CHECK (path_index BETWEEN 1 AND 3),
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 5),
    name TEXT NOT NULL,
    cost INTEGER NOT NULL CHECK (cost >= 0),
    UNIQUE (tower_id, path_index, tier)
);
