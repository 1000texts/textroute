Dynamic social graph + latent community detection pipeline

You need three layers:
Raw interaction storage (facts, append-only)
Derived graph representations (edges + weights)
Learned representations (embeddings → factions)

Events → Graph → Embeddings → Communities (factions)

At load:
Nodes = people
Edges = interaction strength


weight = Σ (interaction_weight × exp(-λ × age))


New interactions
      ↓
Update graph_edges
      ↓
Recompute embeddings (batch or incremental)
      ↓
Recompute faction memberships
      ↓
Store results

Not started:
- graph_native.py — native graph storage / ops (placeholder removed until implemented)
