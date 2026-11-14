CREATE TABLE towers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL
);

CREATE TABLE damage_types (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    can_pop_lead INTEGER CHECK (can_pop_lead IS NULL OR can_pop_lead IN (0, 1)),
    can_pop_black INTEGER CHECK (can_pop_black IS NULL OR can_pop_black IN (0, 1)),
    can_pop_white INTEGER CHECK (can_pop_white IS NULL OR can_pop_white IN (0, 1)),
    can_pop_purple INTEGER CHECK (can_pop_purple IS NULL OR can_pop_purple IN (0, 1)),
    can_pop_glass INTEGER CHECK (can_pop_glass IS NULL OR can_pop_glass IN (0, 1)),
    can_pop_frozen INTEGER CHECK (can_pop_frozen IS NULL OR can_pop_frozen IN (0, 1))
);

-- Generated from btd6.etl.extract.DAMAGE_TYPES (ids follow bitmask order); Unknown flags are NULL.
INSERT INTO damage_types
    (id, name, can_pop_lead, can_pop_black, can_pop_white, can_pop_purple, can_pop_glass, can_pop_frozen)
VALUES
    (1, 'Normal', 1, 1, 1, 1, 1, 1),
    (2, 'Shatter', 0, 1, 1, 1, 1, 1),
    (3, 'Explosion', 1, 0, 1, 1, 1, 1),
    (4, 'Glacier', 1, 1, 0, 1, 1, 1),
    (5, 'Cold', 0, 1, 0, 1, 1, 1),
    (6, 'Fire', 1, 1, 1, 0, 1, 1),
    (7, 'Frigid', 1, 1, 0, 0, 1, 1),
    (8, 'Sharp', 0, 1, 1, 1, 1, 0),
    (9, 'Acid', 1, 1, 1, 1, 0, 1),
    (10, 'Plasma', 1, 1, 1, 0, 0, 1),
    (11, 'Energy', 0, 1, 1, 0, 0, 1),
    (12, 'Unknown', NULL, NULL, NULL, NULL, NULL, NULL);

CREATE TABLE upgrades (
    id INTEGER PRIMARY KEY,
    tower_id INTEGER NOT NULL REFERENCES towers (id) ON DELETE CASCADE,
    path TEXT NOT NULL CHECK (path GLOB '[0-5]-[0-5]-[0-5]'),
    damage_type_id INTEGER NOT NULL REFERENCES damage_types (id),
    range REAL CHECK (range IS NULL OR range >= 0),
    footprint_radius REAL CHECK (footprint_radius IS NULL OR footprint_radius >= 0),
    attack_rate REAL CHECK (attack_rate IS NULL OR attack_rate >= 0),
    projectile_count INTEGER CHECK (projectile_count IS NULL OR projectile_count >= 0),
    projectile_damage REAL CHECK (projectile_damage IS NULL OR projectile_damage >= 0),
    projectile_pierce REAL CHECK (projectile_pierce IS NULL OR projectile_pierce >= 0),
    projectile_speed REAL CHECK (projectile_speed IS NULL OR projectile_speed >= 0),
    projectile_radius REAL CHECK (projectile_radius IS NULL OR projectile_radius >= 0),
    projectile_lifespan REAL CHECK (projectile_lifespan IS NULL OR projectile_lifespan >= 0),
    can_hit_camo INTEGER NOT NULL CHECK (can_hit_camo IN (0, 1)),
    ability_cooldown REAL CHECK (ability_cooldown IS NULL OR ability_cooldown >= 0),
    UNIQUE (tower_id, path)
);

CREATE INDEX idx_upgrades_damage_type_id ON upgrades (damage_type_id);
CREATE INDEX idx_upgrades_range ON upgrades (range);
CREATE INDEX idx_upgrades_projectile_pierce ON upgrades (projectile_pierce);
CREATE INDEX idx_upgrades_projectile_damage ON upgrades (projectile_damage);
