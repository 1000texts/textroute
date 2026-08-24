# Node embeddings (Node2Vec)
# This allows multiple faction membership implicitly.

from node2vec import Node2Vec
import networkx as nx

G = nx.Graph()
node2vec = Node2Vec(G, dimensions=128, walk_length=30, num_walks=200, workers=4)

model = node2vec.fit(window=10, min_count=1)

embedding = model.wv["some-person-id"]
# Each person now has a dense vector representation.
