from sklearn.mixture import GaussianMixture
import numpy as np
import networkx as nx
from node2vec import Node2Vec

G = nx.Graph()

node2vec = Node2Vec(G, dimensions=64, walk_length=30, num_walks=200, workers=4)

model = node2vec.fit(window=10, min_count=1, batch_words=4)


X = np.array([model.wv[n] for n in G.nodes])

gmm = GaussianMixture(n_components=5)
gmm.fit(X)

memberships = gmm.predict_proba(X)
