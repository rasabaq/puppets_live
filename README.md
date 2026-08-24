# Puppets — screenshot labelling (public MVP)

A small Streamlit app for labelling social-media screenshots for advertising,
food presence, and ultra-processed food (NOVA 4), as part of a sock-puppet
advertising audit. This is a **research MVP**, not a production service:
expect rough edges, and treat the underlying labels as provisional until
reviewed by a human.

## What it does

Upload the screenshots that make up one "unit" (e.g. the frames of a video),
optionally attach the unit's audio, and run the labelling agents. Each
screenshot set is scored for:

- `is_ad` — is this advertising?
- `has_food` — is food present?
- `is_upf` — is the food ultra-processed (NOVA 4)?

See `CODEBOOK.md` for the full variable definitions — the model's prompts
are compiled from that document, so it is the source of truth. It was copied
from **puppets 0.5.0** (see `vendor/VERSION` for the exact source commit);
if the codebook changes upstream, this copy needs to be refreshed too.

Results, a raw JSONL of every model response, and a cost/token summary can
be downloaded from the app. **Nothing is stored server-side** — uploads and
results live only in the browser session and in Streamlit's ephemeral
runtime storage, and disappear when the session ends.

## The call cap

Each browser session is capped at **100 API calls**. This is a courtesy
limit to keep any one session from running away with the shared OpenRouter
key, not a security boundary — the real enforcement is the credit cap set on
the OpenRouter API key itself. If you need to label more than the cap
allows, run more sessions or use the underlying `puppets` library directly.

## Running locally

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Provide an OpenRouter API key, either via a `.env` file in this directory
   (`OPENROUTER_API_KEY=sk-...`) or by pasting it into the app's sidebar at
   runtime. For a Streamlit Community Cloud deployment, set
   `OPENROUTER_API_KEY` in the app's **Secrets**, not in a committed file —
   this repo intentionally does not ship a `secrets.toml` template.

3. Run the app:

   ```bash
   streamlit run app.py
   ```

## Updating the vendored library

This app depends on a prebuilt wheel of the `puppets` library, vendored
under `vendor/` rather than installed from a package index, so the app's
behavior only changes when someone deliberately updates it.

To update:

1. In the source repo, build a fresh wheel: `python -m build --wheel`.
2. Copy the new `dist/puppets-<version>-py3-none-any.whl` into `vendor/`
   here, removing the old one.
3. Update `requirements.txt` to reference the new filename.
4. Update `vendor/VERSION` with the new library version **and** the source
   repo's git commit SHA the wheel was built from
   (`git rev-parse HEAD` in the source repo). This is the only record of
   which library revision is actually deployed — without it, drift between
   the vendored wheel and the source repo becomes unrecoverable.
5. If `CODEBOOK.md` changed upstream, copy the new version too, and update
   the version note above.

## Notes on scope

This app intentionally ships without ffmpeg or any audio transcoding: audio
escalation uploads the user's file directly to OpenRouter's transcription
endpoint, and the library detects format from the file suffix rather than
transcoding, so no system audio/video tooling is required.
