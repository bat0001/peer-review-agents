DeepSeek Lossfree Loading Balancing paper reports MaxViolation. Do we need that?

Did not know that Lossfree actually used I-control. It was just suboptimal implementation.

Good news: I realized that most reference papers did not do that many ablations and comparisons. Some did not even report the benchmark scores.So a handful of baseline is good. 

Experiment design: 
- Global LBL has a good plot of expert usage: 

```
(a) Ablation of Balance Scope (b) Expert Frequency for Micro-Batch Balance (Left) and Global-Batch Balance (Right) 

Figure 1: The impact of the Balance BSZ on (a) model performance and (b) expert specialization. (a) When employing micro-batch level load balance, methods based on LBL and based on auxiliary-loss-free (Wang et al., 2024) approaches perform worse than employing the global-batch balance. (b) When employing micro-batch balance, there is no significant difference in the selection frequency of different domain-specific data, and the selection frequency of different experts within the same domain is approximately the same. With global-batch balance, there is a noticeable difference in the selection frequency of experts on different domain data, and within the same domain, there are experts with high selection frequency (marked in blue).
```