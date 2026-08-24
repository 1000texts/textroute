# At this point:
# Nodes = people
# Edges = interaction strength

import networkx as nx
import psycopg2
from sklearn.mixture import GaussianMixture
import numpy as np
from node2vec import Node2Vec

G = nx.Graph()

conn = psycopg2.connect(...)
cur = conn.cursor()

cur.execute(
    """
    SELECT source_id, target_id, weight
    FROM graph_edges
"""
)

for source, target, weight in cur.fetchall():
    G.add_edge(source, target, weight=weight)


G = nx.Graph()
node2vec = Node2Vec(G, dimensions=64, walk_length=30, num_walks=200, workers=4)
model = node2vec.fit(window=10, min_count=1, batch_words=4)

X = np.array([model.wv[n] for n in G.nodes])

gmm = GaussianMixture(n_components=5)
gmm.fit(X)

memberships = gmm.predict_proba(X)
