# Agent operating contract

This repository builds a user's private interview library. Agents should use the public CLI and treat `data/` as private runtime state.

1. Install with `python -m pip install -e .`.
2. Ask for the target role, then run `interviews-helper collect --job "<role>"`. Add `--keywords` only when the role name is too broad. Add `--url-file` for user supplied public pages.
3. If a site requests authentication, run `interviews-helper login <platform>` and let the user interact with the browser. Never inspect, print, copy, or commit browser profiles or cookies.
4. Resume with the same arguments or the returned `run_id`. Read machine state with `interviews-helper status --json`.
5. Retrieve candidates with `interviews-helper search "<question>" --json`. Cite the returned `sources`; do not present generated questions as collected interview questions without evidence.
6. Keep `data/`, `.browser-profile-*`, downloaded images, real seed files, and generated reports out of Git.

The crawler must stay low frequency. Do not bypass verification, replay private APIs, or automate CAPTCHA handling. Agents may correct OCR, split compound questions, classify topics, and rerank a bounded retrieval set while retaining the original evidence.
