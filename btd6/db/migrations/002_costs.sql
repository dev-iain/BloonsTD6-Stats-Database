ALTER TABLE towers ADD COLUMN base_cost INTEGER;

CREATE TABLE upgrade_costs (
    id INTEGER PRIMARY KEY,
    tower_id INTEGER NOT NULL REFERENCES towers (id),
    path_index INTEGER NOT NULL CHECK (path_index BETWEEN 1 AND 3),
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 5),
    name TEXT,
    cost INTEGER NOT NULL,
    UNIQUE (tower_id, path_index, tier)
);
