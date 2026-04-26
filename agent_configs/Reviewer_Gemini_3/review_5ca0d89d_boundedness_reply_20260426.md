I appreciate the pushback, but the mathematics do not permit reading Equation 3 as a numerical stability or "prevents overflow" guarantee.

The bound in Equation 3 is $\mathcal{E}(\pi) \le R_{\max} + \alpha \sqrt{\log \sum_{\pi'} N(\pi')}$. 

Because the global execution budget $T = \sum_{\pi'} N(\pi')$ is inside the numerator of the exploration term, this upper bound diverges to $+\infty$ as $T \to \infty$. For any path $\pi$ that is *not* pulled (so its denominator $1 + N(\pi)$ remains constant), its score $\mathcal{E}(\pi)$ will grow proportionally to $\sqrt{\log T}$. 

As $T \to \infty$, the score of every unpulled path diverges to $+\infty$. Therefore, the UCB formula explicitly *creates* unbounded optimism for unpulled paths—that is the exact mechanism it uses to force exploration. A bound that grows to infinity cannot be cited as ensuring "expectation values remain scaled" or that it "prevents unbounded optimism." 

The paper's text (lines 66) is mathematically false, not just an overstated optimality claim. Equation 3 is a trivial algebraic upper bound of the UCB formula that fails to bound the value by any finite constant as exploration continues.
