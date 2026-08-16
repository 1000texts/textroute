CREATE TABLE
    interactions (
        interaction_id UUID PRIMARY KEY,
        actor_id UUID NOT NULL REFERENCES members (member_id),
        target_id UUID NOT NULL REFERENCES members (member_id),
        interaction_type TEXT NOT NULL, -- message, reply, help, dispute, etc.
        weight FLOAT DEFAULT 1.0, -- optional strength
        occurred_at TIMESTAMP NOT NULL
    );

CREATE INDEX idx_interactions_actor ON interactions (actor_id);

CREATE INDEX idx_interactions_target ON interactions (target_id);

CREATE INDEX idx_interactions_time ON interactions (occurred_at);

CREATE TABLE
    graph_edges (
        source_id UUID,
        target_id UUID,
        weight FLOAT,
        last_updated TIMESTAMP,
        PRIMARY KEY (source_id, target_id)
    );

CREATE TABLE
    inferred_factions (
        member_id UUID,
        faction_id TEXT,
        membership_strength FLOAT,
        inferred_at TIMESTAMP,
        PRIMARY KEY (member_id,Ï faction_id)
    );