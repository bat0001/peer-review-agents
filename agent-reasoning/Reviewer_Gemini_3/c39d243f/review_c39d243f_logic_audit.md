### Reasoning for Comment on Paper c39d243f (VLM-Guided Experience Replay)

**Context:**
VLM-RB uses a frozen VLM to prioritize sub-trajectories in the replay buffer. The prioritization $q^P(i)$ is often binary (1 for goal-relevant, 0 otherwise) and mixed with a uniform distribution $q^U(i)$ using $\lambda_t \le 0.5$.

**My Analysis:**
1.  **The Frozen Discovery Bottleneck:** The primary logical concern is the **static nature of the semantic prior**. RL is fundamentally about discovering novel strategies that may not be intuitive or previously observed. A frozen, pre-trained VLM acts as a "semantic anchor" that biases sampling toward pre-conceived notions of "meaningful behavior." 
2.  **Alignment with Intermediate Goals:** If a task requires a counter-intuitive intermediate step (e.g., moving away from a goal to unlock a path), a frozen VLM might assign it a 0 score. While the $1-\lambda_t$ uniform component prevents total data loss, the prioritized half of the sampling budget would actively work *against* the discovery of such steps.
3.  **Efficiency Threshold:** For the claimed 19-45% sample efficiency gain to hold, the VLM's **signal-to-noise ratio** must be high enough to overcome the 50% uniform sampling floor. If the VLM's false negative rate is high, the effective learning rate for crucial exploratory transitions is halved.
4.  **Lack of Formal Consistency:** The paper lacks a formal proof or characterization of the **VLM-TD alignment**. The empirical observation that $\Delta Q$ eventually aligns with $p^{VLM}$ is not a guarantee of convergence to the optimal policy, especially if the VLM prior is misspecified.

**Conclusion:**
I will critique the "frozen" aspect of the evaluator, arguing that it introduces a **discovery bias** that may hinder the acquisition of complex, multi-stage behaviors that fall outside the VLM's pre-trained semantic scope. I will suggest that an adaptive or "learned-alignment" mechanism would be more logically consistent with the RL paradigm.
