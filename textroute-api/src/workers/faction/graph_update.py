import networkx as nx
import psycopg2

G = nx.Graph()

conn = psycopg2.connect(...)
cur = conn.cursor()

cur.execute(
    """
INSERT INTO graph_edges (source_id, target_id, weight, last_updated)
SELECT actor_id,
       target_id,
       SUM(weight),
       MAX(occurred_at)
FROM interactions
GROUP BY actor_id,
         target_id ON CONFLICT (source_id,
                                target_id) DO
UPDATE
SET weight = graph_edges.weight + EXCLUDED.weight,
    last_updated = EXCLUDED.last_updated;
"""
)
