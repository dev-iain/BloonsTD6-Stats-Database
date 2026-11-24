CREATE TABLE attacks (
    id INTEGER PRIMARY KEY,
    upgrade_id INTEGER NOT NULL REFERENCES upgrades (id) ON DELETE CASCADE,
    attack_index INTEGER NOT NULL CHECK (attack_index >= 0),
    name TEXT NOT NULL,
    rate REAL CHECK (rate IS NULL OR rate >= 0),
    UNIQUE (upgrade_id, attack_index)
);

CREATE TABLE projectiles (
    id INTEGER PRIMARY KEY,
    attack_id INTEGER NOT NULL REFERENCES attacks (id) ON DELETE CASCADE,
    projectile_index INTEGER NOT NULL CHECK (projectile_index >= 0),
    name TEXT NOT NULL,
    damage REAL CHECK (damage IS NULL OR damage >= 0),
    pierce REAL CHECK (pierce IS NULL OR pierce >= 0),
    unlimited_damage INTEGER NOT NULL DEFAULT 0 CHECK (unlimited_damage IN (0, 1)),
    unlimited_pierce INTEGER NOT NULL DEFAULT 0 CHECK (unlimited_pierce IN (0, 1)),
    moab_bonus_damage REAL CHECK (moab_bonus_damage IS NULL OR moab_bonus_damage >= 0),
    moab_only INTEGER NOT NULL DEFAULT 0 CHECK (moab_only IN (0, 1)),
    count INTEGER CHECK (count IS NULL OR count >= 0),
    speed REAL CHECK (speed IS NULL OR speed >= 0),
    radius REAL CHECK (radius IS NULL OR radius >= 0),
    lifespan REAL CHECK (lifespan IS NULL OR lifespan >= 0),
    damage_type_id INTEGER NOT NULL REFERENCES damage_types (id),
    can_hit_camo INTEGER NOT NULL CHECK (can_hit_camo IN (0, 1)),
    UNIQUE (attack_id, projectile_index),
    CHECK (NOT unlimited_damage OR damage IS NULL),
    CHECK (NOT unlimited_pierce OR pierce IS NULL)
);

CREATE INDEX idx_projectiles_damage_type_id ON projectiles (damage_type_id);
