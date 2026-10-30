# AIZOYA ProofOS

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

Open http://127.0.0.1:8766 on the same computer. Review the prepared sample, enter or edit a claim and excerpt, run the deterministic passage check, and inspect/download its receipt. This command does **not** enable live model inference. Its model panel is unavailable; this is an explicit scope boundary.

## NVIDIA and Nebius integration

`inference_bridge.py` connects the local UI to `runtime/one-shot-r5/run_once.py`. The frozen request uses the Nebius Token Factory chat-completions endpoint, model `nvidia/nemotron-3-super-120b-a12b`, JSON output, and a 1024-token output limit. No GPU instances were provisioned. No Tavily runtime integration or autonomous web retrieval is claimed.

The historical live run required an explicit owner-approved request, fixed persistent reservation, private local key, exact source identities, expiry, and zero retries. Both the original 401 attempt and the separately approved recovery were consumed. The recorded approvals are historical evidence and grant no reader authority to spend. Do not delete/reset reservations, alter the guard, or reuse these approvals. No live invocation is offered as a repeatable judge workflow. Never place API secrets in the browser, repository, or screenshots.

## Source identity and validation

The reviewed runtime is preserved byte-for-byte under app release `sha256:c2b57f4b3b69dc3a7554a84932b5e23db23af652546379d7bd681e28927e101c` and guard `sha256:49aff9f118883edfe9f34067cd548f92bc7f1aa848653b0d10263065f9af5e2f`. `release.json` binds 40 runtime files; README and the added documentation are outside that historical runtime map. See `docs/PACKAGE_AUDIT.json` for this source-package inspection. Hashes establish internal consistency, not who ran tests or approved actions.

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
