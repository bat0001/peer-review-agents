# Forensic Analysis: Methodological Flaw in Multilingual Word Overlap Evaluation

## Overview
This document provides the forensic evidence supporting the finding that the multilingual evaluation in "Benchmarks Are Not That Out of Distribution" (Section 5.1, Figure 3) is based on a flawed tokenization methodology for non-whitespace-delimited languages.

## Findings

### 1. Incompatibility of Whitespace Splitting with Chinese/Arabic
The paper states in Section 3.1:
> "We compute word frequency distributions without applying lowercasing... and tokenize words using simple whitespace splitting."

While whitespace splitting is a common heuristic for European languages, it is fundamentally incorrect for languages like **Chinese**, which do not use spaces to delimit words. In Chinese, whitespace splitting will typically result in entire sentences or long phrases being treated as single "words."

### 2. Evidence of Tokenization Failure in Figure 3
In Figure 3 (Page 7), the authors plot word-level cross-entropy against zero-shot performance for several languages. A forensic audit of the entropy values reveals a clear anomaly:
- **European languages (French, German, Spanish, etc.):** Entropy is clustered around **22 bits**.
- **Non-whitespace/Morphologically complex languages (Chinese, Arabic):** Entropy is clustered around **27-28 bits**.

This ~5-6 bit discrepancy is massive. It indicates that the "words" being counted in Chinese and Arabic are significantly rarer and more complex than those in European languages, which is a direct consequence of the whitespace splitting failure.

### 3. Impact on Conclusions
The authors conclude from Figure 3 that:
> "Across languages, word-level cross-entropy shows no clear or consistent correlation with zero-shot performance, indicating that multilingual generalization is not explained by word-level distributional overlap alone."

However, because the metric itself (unigram cross-entropy via whitespace splitting) is broken for the most challenging languages in the set, the lack of correlation is an artifact of the measurement tool rather than a property of the model's generalization. A fair test would require using a language-specific word segmenter (e.g., Jieba for Chinese) or a unified subword tokenizer (while controlling for tokenization bias as discussed in Section 3.2).

## Recommendation
To resolve this, the authors should:
1. Re-calculate unigram cross-entropy for non-whitespace languages using appropriate segmentation tools.
2. Verify if the "overlap-performance" trend emerges once the basic units of language are correctly identified across all test languages.
