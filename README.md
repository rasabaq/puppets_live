# Puppets — screenshot labelling (public MVP)

A small Streamlit app for labelling social-media screenshots for advertising,
food presence, and ultra-processed food (NOVA 4), as part of a sock-puppet
advertising audit. This is a **research MVP**, not a production service:
expect rough edges, and treat the underlying labels as provisional until
reviewed by a human.

## What it does

Upload the screenshots that make up one "unit" (e.g. the frames of a video)
and run the labelling agents. Each screenshot set is scored for:

Four independent ad-disclosure sub-variables — there is no single `is_ad`
flag any more, because "is this an ad?" turned out to be four different
questions with different answers:

- `ad_paid_promotion` — was the *platform* paid to distribute this?
- `ad_paid_advertising` — is a platform-rendered disclosure banner visible?
- `ad_brand_owned` — is the posting account the brand itself?
- `ad_undisclosed` — is it commercial content with no disclosure at all?
  (Null, not 0, whenever one of the three above is 1.)

Plus food and description:

- `has_food` — is food present?
- `is_upf` — is the food ultra-processed (NOVA 4)?
- `food_category` — which of eight dietary food groups?
- `foods` — the specific foods and drinks on screen.
- `brands` — the brand or brands that paid for the promotion.

`food_category`, `foods` and `brands` each distinguish three states in the
results and in `labels.csv`: `null` means the agent was never asked, `[]`
means it was asked and found nothing nameable, and a value names what it
found. That distinction is a finding in itself, so it is never flattened.

See `CODEBOOK.md` for the full variable definitions — the model's prompts
are compiled from that document, so it is the source of truth. It was copied
from the source repo (see `vendor/VERSION` for the exact version and commit);
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
behavior only changes when someone deliberately updates it. A vendored wheel
also means the build needs no credentials: the library's own repository is
private, and installing from it would otherwise require an access token.

The update is driven from the **source repo**, not from here:

```bash
cd ../puppets                       # the private library repo
git commit -am "feat: ..."          # the release refuses a dirty src/
scripts/release_to_live.sh patch    # or: minor, major, or an explicit 0.7.2
```

That bumps the library version, runs its packaging guards, builds the wheel,
copies it into `vendor/` here, rewrites `vendor/VERSION` and the pin in
`requirements.txt`, and runs this app's tests against the new wheel. It stops
before committing, so review and ship yourself:

```bash
git status --short
git add -A && git commit -m "chore: bump puppets to <version>"
git push
```

Streamlit Cloud redeploys on push. Confirm the build log installs the new
wheel filename before trusting the change is live.

**The version must always change.** Rebuilding a wheel under a version that
is already installed lets pip skip it as already-satisfied, so the deployed
app keeps running the old library while this repo says it was updated. The
release script bumps it for you; if you ever do this by hand, do not skip it.

`vendor/VERSION` records the library version **and** the source commit it was
built from. That is the only record of which revision is actually deployed —
when a result here looks wrong, it names the exact commit to go look at.

If `CODEBOOK.md` changed upstream, copy it across too; it is a copy, not a
shared file, and will otherwise drift.

## Notes on scope

This app labels frames only — there is no audio upload. The audio channel
escalated to a spoken-disclosure verdict that flipped the old `is_ad` flag,
and now that `is_ad` is decomposed into the four sub-variables above, none of
them is a spoken disclosure for that verdict to set. The library disables the
channel outright (`Config.audio_escalation` raises rather than silently doing
nothing). The uploader comes back here when a spoken-sponsorship sub-variable
lands upstream.

This also means the app still needs no ffmpeg or audio transcoding, and no
system audio/video tooling of any kind.
