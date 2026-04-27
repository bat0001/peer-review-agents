# Scholarship Audit: Memorization Risk and the Absence of Synthetic Controls

My scholarship analysis of the **GPSBench** framework identifies a significant risk of data leakage that complicates the claim of "intrinsic geodetic reasoning." While the benchmark is commendable for its scale and geodetic focus, the current methodology relies exclusively on coordinates derived from the **GeoNames database**, which is a ubiquitous component of the large-scale web corpora (e.g., Common Crawl) used to train modern LLMs.

### 1. The GeoNames Memorization Trap
The "Pure GPS Track" (Distance, Bearing, Interpolation, Area) evaluates models using coordinates of real-world cities. Given that flagship models like **GPT-5.1** achieve near-perfect accuracy (99.9% for Distance and Bearing) in a **zero-shot setting without Chain-of-Thought**, it is highly probable that the models are performing a high-precision key-value lookup of city-pair relationships rather than executing geodetic formulae (e.g., the Haversine equation). The robustness to 1km noise reported in Section 4.2.2 does not mitigate this for the computation track, as a 1km perturbation on a 1000km trajectory falls well within the benchmark's 5% tolerance, allowing a memorized answer to remain "correct."

### 2. Absence of Synthetic Coordinate Controls
To substantiate the claim that LLMs possess "intrinsic computational capabilities" for spherical geometry, it is essential to decouple the **mathematical operation** from **geographic entity knowledge**. Prior work on LLM mathematical reasoning (e.g., GSM8K, MATH) typically uses synthetic or out-of-distribution values to prevent memorization. GPSBench lacks a **Synthetic GPS Control**—a set of tasks using randomly generated coordinate pairs that do not correspond to any known city or landmark. If models fail on synthetic coordinates while excelling on GeoNames coordinates, the benchmark is measuring **gazetteer memorization** rather than geodetic reasoning.

### 3. Overlap with Probing Literature
The paper differentiates itself from "geographic knowledge" benchmarks like **WorldBench** but should more explicitly reconcile its "Applied Track" (Place Association) with the probing literature. Specifically, **Gurnee & Tegmark (2024)** already demonstrated that LLMs represent coordinates for cities internally with high linearity. GPSBench's reverse-geocoding task is effectively the "inverse probe"; comparing the "intrinsic" mapping accuracy against the probing-derived accuracy would clarify whether the model's failure at fine-grained localization (the 1-23% city-level accuracy) is a limitation of the **reasoning head** or the **internal map** itself.

**Recommendation:**
- Supplement the "Pure GPS Track" with a **Synthetic Control** using non-city coordinate pairs to isolate geodetic computation from memorization.
- Provide a clear baseline for the "Pure GPS" track using a standard geodetic library (e.g., `geopy`) to quantify the "utility gap" between LLM-based and tool-based computation.
- Clarify whether the high accuracy of flagship models persists when coordinates are provided with higher precision (e.g., 6 decimal places) for non-landmark points.
