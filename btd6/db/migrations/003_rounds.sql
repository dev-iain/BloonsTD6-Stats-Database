CREATE TABLE bloons (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    health INTEGER CHECK (health IS NULL OR health >= 0),
    health_fort INTEGER CHECK (health_fort IS NULL OR health_fort >= 0),
    layers INTEGER CHECK (layers IS NULL OR layers >= 0),
    rbe INTEGER CHECK (rbe IS NULL OR rbe >= 0),
    rbe_fort INTEGER CHECK (rbe_fort IS NULL OR rbe_fort >= 0),
    is_moab INTEGER NOT NULL CHECK (is_moab IN (0, 1)),
    speed REAL CHECK (speed IS NULL OR speed >= 0)
);

CREATE TABLE rounds (
    round INTEGER PRIMARY KEY CHECK (round >= 1)
);

CREATE TABLE round_groups (
    id INTEGER PRIMARY KEY,
    round INTEGER NOT NULL REFERENCES rounds (round) ON DELETE CASCADE,
    group_index INTEGER NOT NULL CHECK (group_index >= 0),
    bloon_id INTEGER NOT NULL REFERENCES bloons (id),
    is_camo INTEGER NOT NULL CHECK (is_camo IN (0, 1)),
    is_regrow INTEGER NOT NULL CHECK (is_regrow IN (0, 1)),
    is_fortified INTEGER NOT NULL CHECK (is_fortified IN (0, 1)),
    count INTEGER NOT NULL CHECK (count > 0),
    start REAL NOT NULL,
    duration REAL NOT NULL CHECK (duration >= 0),
    UNIQUE (round, group_index)
);

CREATE INDEX idx_round_groups_round ON round_groups (round);
CREATE INDEX idx_round_groups_bloon_id ON round_groups (bloon_id);
