CREATE TABLE projectile_effects (
    id INTEGER PRIMARY KEY,
    projectile_id INTEGER NOT NULL REFERENCES projectiles (id) ON DELETE CASCADE,
    effect_index INTEGER NOT NULL CHECK (effect_index >= 0),
    name TEXT NOT NULL,
    damage REAL NOT NULL CHECK (damage > 0),
    tick_interval REAL NOT NULL CHECK (tick_interval > 0),
    lifespan REAL NOT NULL CHECK (lifespan >= 0),
    trigger_immediate INTEGER NOT NULL CHECK (trigger_immediate IN (0, 1)),
    moab_bonus_damage REAL CHECK (moab_bonus_damage IS NULL OR moab_bonus_damage >= 0),
    moab_only INTEGER NOT NULL DEFAULT 0 CHECK (moab_only IN (0, 1)),
    damage_type_id INTEGER NOT NULL REFERENCES damage_types (id),
    UNIQUE (projectile_id, effect_index)
);

CREATE INDEX idx_projectile_effects_damage_type_id ON projectile_effects (damage_type_id);
