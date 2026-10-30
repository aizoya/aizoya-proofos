# Tavily retrieval successor — October 30, 2026

This successor adds owner-local Tavily Search to the existing ProofOS judge app. **Implemented and offline tested; live Tavily execution has NOT run.** It does not renew or reuse either Nebius attempt. The recorded Nemotron response still applies only to its original operator-supplied passage. No new model assesses retrieved search text.

Start with `python3 tools/serve_research.py --preflight` to verify the release and print the exact request plus an **unapproved** approval template. This does not load credentials, access an owner reservation, write a ledger, or call Tavily.

`python3 tools/serve_research.py` starts the app on loopback with retrieval locked. The live path requires an external exact-candidate GO, explicit owner credit-only approval, one available Tavily credit, a private shell `TAVILY_API_KEY`, and a completed approval file passed with `--approval-file`. Do not put a key in an approval file, source, URL, screenshot, or chat. `--approval-file` alone does not initiate a request; the owner must click the prepared-search button once while the service reports ready.

The fixed query searches only organizer pages, Basic depth, up to three results, no generated answer, no images/raw HTML, automatic parameter selection off, usage reporting on, and max_age_hours=0. Tavily documents one API credit for Basic Search; this is not a provider-enforced billing cap. Account balance and overage settings are not verified by this code. No paid overage is authorized. Do not approve unless an included credit remains available.

The new fixed persistent reservation is `~/.aizoya/proofos/tavily-search-20261030-01.json`, resolved through the OS account record rather than HOME. This is a separate proposed Tavily authority, not a reset of Nebius. The guard uses the frozen R5 directory-pinning and atomic-persistence helpers; it never opens the two consumed Nebius reservations. One failed/uncertain request consumes the Tavily attempt. Preserve its record and terminal evidence; do not delete or relocate it to retry. Owner-local POSIX only. Ephemeral Vercel storage is not an acceptable live reservation store.

The hosted static app remains safe without a live search route. No Vercel `/api/research` function or public paid endpoint is added. The `serve_research.py` bridge is loopback-only and checks Host, Origin, custom header and bounded request before execution. Default local `tools/serve.py` still supports the deterministic review and recorded model viewer, with Tavily unavailable.

Search cards show untrusted excerpts and original links. “Use this source” loads its excerpt and link into the passage-check form, clears the old result and quotation, and asks the user to select an exact quote. The resulting deterministic receipt describes operator-selected text, not independently authenticated retrieval. The separate retrieval receipt carries request identity, response evidence, sources, source hashes, observed credits, timestamps and limitations. Download both for reconciliation. Search completion is NEEDS_REVIEW and fully_verified remains false.

Tavily search excerpts are not proof of original page authenticity, publication date, factual support or absence of contradictions. Retrieval timestamps record the app's observation time, not publication time. Provider-reported credits are not an independently verified invoice. Network timeout is per I/O; direct proxies are disabled; no retries or redirects. Response bodies are bounded at 256 KiB, checkpointed before validation, and may contain public untrusted text. No analytics added.

## Offline verification

- `python3 tools/verify.py`
- `python3 -m unittest discover -s tests -v`
- `python3 -m unittest discover -s runtime/one-shot-r5 -v`
- `node tools/test_recorded.cjs`
- `node tools/test_research.cjs`
- `python3 tools/serve_research.py --preflight`

All test transport injection is Python-only and marked TEST_DOUBLE, with zero provider calls. No fake runtime evidence is shipped as an observed Tavily result. A real browser, mobile/Safari, hosted acceptance, actual credit balance and live Tavily behavior remain unverified until exercised. The parent review records below remain historical. F4/F5, release and submission gates remain open.

Official API and pricing references checked October 30, 2026:
https://docs.tavily.com/documentation/api-reference/endpoint/search
https://docs.tavily.com/documentation/api-credits

---

## Historical parent documentation

# AIZOYA ProofOS — judge presentation candidate

This is a successor presentation candidate, not the already reviewed R5 application. Its new app release is `sha256:a0b6d19d2b2f7795bc05ad491f77ee2d1aa5e91d3b3c1ba0a3b19c8748d906d3`. The original R5 provider receipt retains its historical release identity. No new inference grant is created.

Judges can interact with a deterministic passage checker and inspect/download a clearly labeled recorded live Nebius/NVIDIA response. The recorded response is never represented as fresh analysis of the judge’s edited text. Its packaged hash establishes byte consistency, not provider provenance. Both paid attempts remain consumed.

Run `python3 tools/serve.py --port 8766` and open http://127.0.0.1:8766. No key is needed. `node tools/test_recorded.cjs` checks the actual recorded-result script with DOM doubles, tampering and error cases; it is not a real-browser test.

The production custom-domain path requires `PROOFOS_PUBLIC_ORIGIN=https://proofos.aizoya.com`. Preview deployments use the existing platform-origin resolver. Public access, DNS/TLS and deployed acceptance are not established by source preparation.

AI that doesn’t just say it’s done. It proves it.

ProofOS is an evidence-review prototype that separates quotation matching, AI assessment, and authorization. A quotation appearing in supplied text does not establish that a claim is true.

## What actually ran

The owner-local backend completed one NVIDIA `nvidia/nemotron-3-super-120b-a12b` request through **Nebius Token Factory**. The supplied excerpt gave October 30 at 10 AM PT but omitted the claimed year. Nemotron returned **INSUFFICIENT**; the receipt remains **NEEDS_REVIEW**, `fully_verified: false`.

Inspect [the observed application receipt](docs/observed-live-run.json). It records HTTP 200, response ID `chatcmpl-b1ffe3497e224cc7`, 263 prompt tokens and 262 completion tokens. Guard elapsed was 1860.576 ms, including evidence persistence, not pure model latency. Estimated token cost was USD 0.0003147; invoice and taxes are unverified. This is one observed run, not a performance benchmark or signed third-party attestation.

## Run the deterministic workflow locally

Python 3.12 or later is recommended. The deterministic local path uses Python standard-library modules; no package installation or key is required.

```bash
python3 tools/verify.py
python3 -m unittest discover -s runtime/one-shot-r5 -v
python3 -m unittest discover -s tests -v
python3 tools/serve.py --port 8766
```

Open http://127.0.0.1:8766 on the same computer. Review the prepared sample, enter or edit a claim and excerpt, run the deterministic passage check, and inspect/download its receipt. This command does **not** enable live model inference. Its model panel reads the historical recorded receipt only; live inference remains unavailable.

## NVIDIA and Nebius integration

`inference_bridge.py` connects the local UI to `runtime/one-shot-r5/run_once.py`. The frozen request uses the Nebius Token Factory chat-completions endpoint, model `nvidia/nemotron-3-super-120b-a12b`, JSON output, and a 1024-token output limit. No GPU instances were provisioned. No Tavily runtime integration or autonomous web retrieval is claimed.

The historical live run required an explicit owner-approved request, fixed persistent reservation, private local key, exact source identities, expiry, and zero retries. Both the original 401 attempt and the separately approved recovery were consumed. The recorded approvals are historical evidence and grant no reader authority to spend. Do not delete/reset reservations, alter the guard, or reuse these approvals. No live invocation is offered as a repeatable judge workflow. Never place API secrets in the browser, repository, or screenshots.

## Source identity and validation

The original provider run used app release `sha256:c2b57f4b3b69dc3a7554a84932b5e23db23af652546379d7bd681e28927e101c` and guard `sha256:49aff9f118883edfe9f34067cd548f92bc7f1aa848653b0d10263065f9af5e2f`. The successor changes presentation/static-serving files and adds the recorded receipt assets; its new `release.json` binds 42 files. The R5 inference guard and provider transport stay unchanged. README and added documentation remain outside that runtime map. See `docs/PACKAGE_AUDIT.json` for this source-package inspection. Hashes establish internal consistency, not who ran tests or approved actions.

Prior author and supplied reviewer results report 48 guard tests, 16 backend tests and 22 VM/loopback journey assertions. Those results are not native Safari, accessibility, hosted multi-tenant security or business-outcome acceptance.

## Honest limitations

- Input is operator-supplied; the app does not authenticate or retrieve the original source.
- Quotation matching is deterministic. Model semantic assessment remains untrusted and subject to human review.
- Original source authenticity/date, cross-source contradictions and business outcomes remain incomplete.
- The Vercel function is the separate deterministic path. The live owner-local inference path is not deployed on Vercel.
- F4/F5 and broader product/release acceptance remain open. This package is not submission acceptance.

## Provider feedback

Managed Token Factory API access enabled a focused Nemotron assessment without GPU provisioning. The successful response followed the structured-output contract, identified omitted support and included useful model/usage metadata. Credential onboarding was confusing: a service-account identifier was initially mistaken for its API secret and produced a 401. Clearer identifier/secret copy guidance and model-specific structured-output/reasoning-budget examples would improve the experience. We would continue evaluating the workflow; one successful case does not establish broad reliability or comparative superiority.

## License

MIT; see [LICENSE](LICENSE). The project owner confirmed this is a new project with no version before August 26, 2026.

## Final QA reconciliation — October 30

A supplied Claude review of the parent app c2b57f4b / commit440ce925 returned MODIFY for stale pre-run UI copy and receipt/governance documentation. Its executed 48 R5,16 app and40 R4 tests belong to that parent review, not this presentation delta. This successor replaces the outdated live-attempt panel with the recorded-result workflow; it still requires a new exact-candidate review.

The nested `source_review` is the deterministic sub-check. Its zero-provider-call count and live-inference NOT_CHECKED entry apply only to that component. The outer receipt holds the observed model call. `task_id` is a display identifier generated after execution and does not identify the persistent run ledger. Reconciliation uses the retained ledger plus provider `response_id`. The original receipt is preserved unchanged; do not treat its nested check as whole-workflow verification. Persisting a canonical task ID would be a separate runtime change requiring review.

Guard elapsed includes the post-response checkpoint write. Initial reservation and final terminal writes are outside the timer. The original receipt wording remains historical; this clarification controls presentation of its timing.

See [the pre-run acceptance-note supplement](docs/R5_PRE_RUN_REVIEW_RECORD.md) for the source artifact missing from the earlier packet. It is author-recorded evidence of a supplied GO, not signed external-review provenance; that distinction remains subject to reviewer acceptance. Do not retroactively treat the latest review as execution authorization.

The filesystem guard tests need POSIX capabilities, including `pwd`, `dir_fd`, FIFO and no-follow support. Unsupported platforms are not accepted by these results.
