---
name: dictation
description: >
  Sets up offline voice dictation for the review page's text fields and manages its speech models -- Whisper on this
  machine, nothing sent anywhere. Nothing is installed until this is run. Trigger: "/craftsman:dictation",
  "set up dictation", "install the dictation engine", "list dictation models", "switch the dictation model".
argument-hint: "setup | list | add <model> | remove <model> | use <model> | status"
allowed-tools: [Bash]
---

# dictation

Runs `scripts/dictation.py` -- see `REVIEW.md`, "Dictation" for what the engine is, where it lives and what it may
download.

## Run this

1. `$ARGUMENTS` empty → treat it as `status`.
2. `setup` → run `python3 <this plugin's own path>/scripts/dictation.py setup` with a timeout of 20 minutes: it
   builds the engine's virtual environment and downloads the default model, about 0.7 GB in all, and prints what it
   did. Relay its last line. A failure prints `dictation: <why>`; relay it as-is -- a run cut short leaves nothing
   half-usable, and running `setup` again continues where it stopped.
3. `list`, `status`, `add <model>`, `remove <model>`, `use <model>` → run `dictation.py <the same arguments>` (`add`
   with a 20-minute timeout) and show its output as-is.

## Notes

- This is the only command that touches the network for dictation. pip and the downloads honour HTTPS_PROXY and a
  CA bundle named by REQUESTS_CA_BUNDLE, SSL_CERT_FILE or PIP_CERT; HF_ENDPOINT names a Hugging Face mirror.
- A model change takes effect on the next dictation; the dashboard restarts the engine by itself.
