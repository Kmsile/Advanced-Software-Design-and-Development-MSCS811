# Evaluation protocol

MSCS811 Advanced Software Design and Development. Defined 12 November 2026 before model generation and implementation.

The case study is the Java extraction component adapted from *Multimodal Phishing Detection under Non-Random Information Loss*. The unit of comparison is an executable test scenario on the same Java code. The research question is whether a requirements-guided test-first prompt changes the fault detection of a small LLM-drafted test suite compared with a direct prompt.

## Fixed change requests

**H. Optional HTML fallback in the hybrid extractor.** The two-argument constructor retains its strict behavior. A third argument, `HybridTextExtractor.OcrFailurePolicy`, selects `PROPAGATE` or `RETURN_HTML`. The result on success is `[HTML]\n<html text>\n[OCR]\n<ocr text>`, with each strategy called once. Only an OCR `IOException` permits HTML-only output in `RETURN_HTML` mode, as `[HTML]\n<html text>`. HTML failure stops before OCR; strict mode, runtime exceptions, and OCR interruption propagate. An interrupted caller retains its interrupt status.

**T. Exclude inactive content from HTML extraction.** Text is the jsoup body text after removing `script`, `style`, `noscript`, `template`, and any element with a `hidden` attribute, including its subtree. Active nested text and entity decoding follow the existing jsoup body text behavior. This is a static text extraction rule.

## Suites and process

- Baseline: the six local checks from the previous Java project. Its two integration checks invoke real OCR and are outside this controlled experiment.
- Direct: three H and three T scenarios drafted with a direct prompt.
- XP-guided: three H and three T scenarios drafted with explicit acceptance-criterion tracing, with the same contract, schema, model, seed and budget. Each generation is a fresh local request. The model receives the requirements and no fault list or reference test results.
- Contract checks: a separate requirement-derived suite drafts the acceptance checks for the red, green and refactor stages. It uses the same local test harness and is a verification oracle, separate from the two scored prompt conditions.

Run the scenarios against the original behavior with an API-compatible constructor scaffold. Record the red tests. Implement both requests, run all tests, and refactor after green. Retain exact prompts, raw model responses, scenarios, stage outputs, settings and model digest.

## Scoring

Use an identical clean version and fixed single-fault variants for all suites. A generated scenario is eligible if its expected result is supported by the contract, it passes the clean implementation, and it is distinct within its suite. Record all invalid or duplicate cases without replacement. A variant is detected when at least one eligible test observes a mismatch. Keep execution errors separate from test mismatches. Compare the three suites and the incremental reach when each generated suite is added to the baseline.

Faults fixed in scope before scoring: disable the opt-in fallback; ignore strict mode; mislabel the fallback output; ignore interruption; duplicate the OCR call; lose the OCR label on success; retain template contents; retain hidden content; drop visible span text; swallow an HTML input failure. All variants represent synthetic functional faults in the local coursework component.

Report raw counts and matched outcomes. A single paired generation with one local model supports a descriptive comparison. The existing baseline is a prior regression suite, with its original provenance. A budget-matched human comparison, estimates of developer time saved, and generalization across models would require separate evidence.
