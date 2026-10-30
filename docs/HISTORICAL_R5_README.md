# AIZOYA ProofOS credential recovery R5

App: sha256:c2b57f4b3b69dc3a7554a84932b5e23db23af652546379d7bd681e28927e101c
Guard: sha256:49aff9f118883edfe9f34067cd548f92bc7f1aa848653b0d10263065f9af5e2f

One prior live request returned HTTP 401. The owner reports using a service-account ID instead of its secret. The original reservation stays untouched; recovery requires matching its persisted state to the bound supplied receipt and reserving the separately approved fixed recovery record. Corrected credential validity is not established until a provider response. Additional request authorization is conditional on offline tests and external review; no exact GO received for this candidate.

One additional unchanged request, 1024 output tokens, zero retries, USD 0.05 estimated additional budget (not provider-enforced), expiry October 30 7 AM Pacific. Prior request cost unknown. The 30 second timeout is per I/O. Truncation risk remains. Fully verified false; F4/F5 and submission HOLD. No Vercel inference or release authority.

## Offline commands

From this folder:
```bash
python3 tools/verify.py
python3 -m unittest discover -s runtime/one-shot-r5 -v
python3 -m unittest discover -s tests -v
python3 runtime/one-shot-r5/run_once.py --expected-candidate sha256:49aff9f118883edfe9f34067cd548f92bc7f1aa848653b0d10263065f9af5e2f
```

From the package folder: `python3 qa_app_driver.py`. This runs app JavaScript in a VM with DOM doubles and loopback HTTP, a fake transport, and temporary synthetic prior/recovery ledgers. It is not browser or live-provider acceptance. No live execution instructions are supplied until external review passes. Do not delete the old reservation or edit frozen R4.
