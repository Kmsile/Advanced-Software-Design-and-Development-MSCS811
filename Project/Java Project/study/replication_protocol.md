# Paired prompt experiment protocol

Frozen on 14 November 2026 before the replication outputs were generated. The 12 November run served as an exploratory pilot. Its two saved responses and results are kept in the coursework archive and excluded from the replication estimates.

## Question and scope

Does adding acceptance-criterion tracing and test-first guidance to a shared requirements prompt change the faults detected by a fixed-budget, model-drafted unit test suite? The comparison concerns scenario selection and assertions for two changes in the existing Java extraction component. The change requests, six inherited local checks, 11 contract verification checks, and ten single-fault variants are the same as in the pilot. The model receives the change contracts and response schema. Source code, fault recipes, reference cases and test outcomes are outside the generation prompt.

## Fixed design

- Check the installed Qwen3.6 digest against the pilot receipt. Use the same local Ollama runtime for both conditions, with thinking disabled, temperature 0.6, top-p 0.9, top-k 40, a 4,096-token context limit and a 2,000-token output limit.
- Use seeds 812 through 835 inclusive. Each seed pairs a direct request and an XP-guided request. Start with direct on even seeds and guided on odd seeds. Calls are stateless and use the same schema and allowance of three hybrid plus three HTML scenarios per suite. The instructions differ only in the final prompt paragraph. Warm the model once before the experiment.
- Make one generation per condition and seed, and archive the exact request and returned response. A response received from the model is final for that cell, including malformed or incomplete output. Retry a local transport failure once and record it. An unavailable cell is reported as missing, with a complete-pair sensitivity summary.
- Validate each returned candidate for its expected schema, permitted local fixture scope, contract-consistent hybrid expectation, exact within-suite duplication and agreement with the correct implementation. HTML expectation agreement is an operational oracle check. Inspect representative outputs against the prose requirements. A returned but unusable case contributes no positive detection. Keep the six-slot allowance fixed. Preserve diagnostics and keep execution failure distinct from a behavioral mismatch.

## Outcomes

The primary outcome is the count of the ten fixed variants detected by each suite, with detection defined as a valid clean-passing case that fails the variant at an assertion. Use the seed as the repeated unit. Report the paired mean difference in faults detected (guided minus direct), the median and range of counts, and guided wins, ties and losses. A paired percentile bootstrap of 10,000 resamples using seed 20261114 summarizes variation over the observed seed pairs. It is conditional on this model, component, change set and fault panel.

Secondary outcomes are the paired detection set overlap, per-fault detection frequency, the score after union with the inherited checks, eligible-case counts, acceptance-criterion prefixes in eligible case names, and failures that expose missing behavior at the Red stage. A name prefix measures explicit annotation and is not evidence that the full criterion was asserted. Record the two prompt orders separately as a sensitivity summary. Use descriptive analyses only. The contract suite verifies that all included faults are distinguishable and is not a human comparison arm.

The fixed fault panel is a diagnostic set of synthetic functional faults. No claim about deployment, developer time saved, real defect incidence, or model generalization follows from this exercise.
