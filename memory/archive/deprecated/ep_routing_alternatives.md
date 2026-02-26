# Archived: EP Routing Alternatives

**Archived**: 2025-12
**Reason**: Over-engineered for our use case. See `memory/plans/expert_parallel_implementation.md` for the simplified approach using All-Gather Logits for training and replicated cutoff_ema for inference.

---

## A. Distributed Exact Top-K (Scalable Exactness)

Instead of gathering all logits, we gather only the "Top-K Candidates" from each rank. This reduces communication from $O(N_{global} \cdot E)$ to $O(P \cdot N_{global})$ (assuming $E \approx P$), or more accurately $O(P^2 \cdot k_{global})$. Since $k_{global} \approx N_{global}/E$, comms $\propto N_{global} \cdot (P^2/E)$. If $E > P^2$, this is much smaller.

**Algorithm:**
1. **Local Candidates**: Each rank computes top-$k$ for each expert from its local tokens.
2. **Gather Candidates**: All-gather these candidates (values + global indices).
3. **Global Reduction**: Each rank merges candidates to find true global top-$k$.

```python
def parallel_forward_distributed_topk(self, x_local):
    # 1. Local Routing
    logits_local = self.router(x_local)  # (N_local, E)

    # 2. Local Top-K Candidates
    # We need top-k candidates for EACH expert from local tokens.
    # Note: k here is the GLOBAL k per expert (e.g., N_global / E).
    # Safety: If a token is in global top-k, it MUST be in the local top-k
    # of the rank that owns it.

    k = self.k_global  # e.g. (B_global * T) // E

    # Local selection: (E, k)
    # This gives the best 'k' tokens this rank has for each expert
    l_values, l_indices_local = torch.topk(logits_local.t(), k=min(k, self.n_tokens_local))

    # Convert to global indices for identification
    l_indices_global = l_indices_local + self.dp_rank * self.n_tokens_local

    # 3. All-Gather Candidates
    # Gather (E, k) from all P ranks -> (P, E, k)
    # We communicate (values, indices) pairs
    # Total size: 2 * P * E * k * sizeof(float/long)
    # Since E*k ~= N_global, size is approx 2 * P * N_global

    all_values = all_gather(l_values)      # (P, E, k)
    all_indices = all_gather(l_indices_global) # (P, E, k)

    # Reshape to list of candidates: (E, P*k)
    cand_values = all_values.permute(1, 0, 2).flatten(1)
    cand_indices = all_indices.permute(1, 0, 2).flatten(1)

    # 4. Global Reduction (Redundant but cheap)
    # Select top k from the P*k candidates per expert
    g_values, g_selection = torch.topk(cand_values, k=k)

    # Retrieve the global indices of the winners
    topk_indices = cand_indices.gather(1, g_selection) # (E, k)

    # 5. Proceed to Compute Dispatch Indices (same as Step 4 in main plan)
    # ...
```

**Why not used**: Only works for top-k mode, adds merge complexity, marginal communication savings for typical batch sizes.

---

## B. Global Histogram Routing (Scalable & Exact)

To avoid gathering all logits or candidates, we use histograms to find the global $k$-th value threshold.

**Algorithm:**
1. **Local Histogram**: Bin logits into $M$ bins (e.g., 1024) across the dynamic range.
2. **Global Reduction**: All-reduce histograms to get global counts per bin.
3. **Global Threshold**: Find the bin containing the $k$-th token.
4. **Local Selection**: Select tokens above the cutoff. Handle boundary ties if strict capacity is required.

```python
def parallel_forward_histogram(self, x_local):
    # 1. Compute Local Histograms
    # dim: (E, bins)
    hist_local = compute_histogram(self.router(x_local), bins=1024)

    # 2. All-Reduce to get Global Histogram
    hist_global = all_reduce(hist_local, op=Sum)

    # 3. Find Cutoff
    # Scan hist_global to find bin index where cumulative count >= k
    cutoff_values = bin_edges[cutoff_bin_indices]

    # 4. Local Selection
    # Select tokens > cutoff_values
    # (Optional) Handle ties for exact k
    # ...
```

**Why not used**: Complex histogram computation, approximate (bin boundaries), harder to debug, not worth the complexity for our scale.

---

## C. Threshold Routing with Global Capacity

If we enforce global capacity constraints while using threshold routing, we face a race condition: multiple ranks might simultaneously fill an expert's capacity.

**Why it's hard:**
- Rank 0 sees 100 tokens > threshold for Expert A.
- Rank 1 sees 100 tokens > threshold for Expert A.
- Expert A capacity = 150.
- Who gets to send? Without global coordination, they don't know.

**Options considered:**
1. **Strict Global Capacity**: All-Reduce counts, then negotiate drops. Expensive, might as well use All-Gather.
2. **Relaxed/Local Capacity**: Enforce capacity per rank. Suboptimal utilization.
3. **No Capacity**: Just process everything above threshold.

**Why not used**: For training we use All-Gather which gives global view for capacity enforcement. For inference, we don't enforce strict capacity.

---

## Original Comparison Table

| Feature | All-Gather Logits | Global Histogram | Threshold + Global Cap | Threshold Inference |
| :--- | :--- | :--- | :--- | :--- |
| **Exactness** | Exact Global Top-K | Exact Global Top-K | Strict Capacity | Approximate |
| **Communication** | High ($N_{global} \cdot E$) | Low ($M \cdot E$) | High (2 rounds) | Tiny ($E$) |
| **Compute** | High (Global sort) | Low (Histogram) | Low | Low |
| **Use Case** | MVP / High Accuracy | Large-Scale Training | N/A (Avoid) | Production Inference |
