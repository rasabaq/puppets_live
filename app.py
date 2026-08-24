"""Streamlit front end for the public screenshot-labelling MVP.

Local:  streamlit run app.py
Cloud:  deploy this repo on Streamlit Community Cloud, set OPENROUTER_API_KEY
        in the app's Secrets, entry point app.py.

This is a research MVP: labelling and codebook only. No benchmarks, no
decision graph, no gold-label editor — those live in the private source
repo this app was extracted from.
"""

from __future__ import annotations

import html
import logging
import tempfile
import threading
import time
from pathlib import Path

import streamlit as st

from puppets import pipeline
from puppets.audio import SUFFIX_TO_FORMAT as AUDIO_SUFFIXES
from puppets.config import DEFAULT_MODE, DEFAULT_MODEL, Config
from puppets.images import SUPPORTED_SUFFIXES
from puppets.logging_setup import setup_logging
from puppets.pipeline import Bundle, run
from puppets.schema import LABEL_FIELDS, REASON_SUFFIX
from puppets.storage import labels_csv, raw_jsonl, summary_json

setup_logging()
logger = logging.getLogger("puppets.app")
logger.info("puppets labelling app started; log level=%s model=%s",
            logging.getLevelName(logging.getLogger("puppets").getEffectiveLevel()),
            DEFAULT_MODEL)

CODEBOOK_PATH = Path(__file__).parent / "CODEBOOK.md"

# Courtesy limit only — the real enforcement is the credit cap on the
# OpenRouter API key. This exists so one browser session cannot run away
# with the shared key while the app is deployed publicly.
MAX_CALLS = 100

LABEL_HINT = {
    "is_ad": {1: "advertising", 0: "organic content", None: "not returned"},
    "has_food": {1: "food present", 0: "no food", None: "not returned"},
    "is_upf": {1: "ultra-processed (NOVA 4)", 0: "NOVA 1-3", None: "not applicable"},
}

# 1 => this reading is the thing the audit is trying to catch; render as a
# flagged (red) finding. 0/None are informational, not a finding.
LABEL_IS_FINDING = {
    "is_ad": {1: True, 0: False, None: False},
    "has_food": {1: False, 0: False, None: False},
    "is_upf": {1: True, 0: False, None: False},
}

AGENT_MODE_CAPTION = (
    "Agent flow: 2-3 calls per unit — ad-detection and food-detection run "
    "concurrently, then UPF classification runs only when food is present."
)

st.set_page_config(page_title="Puppets — screenshot labelling", page_icon="🧪",
                   layout="wide")

# --- Styling -----------------------------------------------------------
#
# Aesthetic: soft porcelain cards floating on a cool ink-tinted gradient,
# one geometric display face (Outfit) against IBM Plex Mono for every
# number. Palette is ink black / porcelain / sea green / punch red / amber
# glow: amber is the single accent (primary actions), sea green means the
# good direction, punch red is reserved for flagged findings (confirmed
# ad, NOVA 4) so it still actually means something. The vivid palette
# values are used for blocks and fills; small text uses the darkened
# siblings (--teal-ink, --red-ink) because #2ec4b6 and #ff9f1c fall to
# roughly 2:1 on porcelain at label sizes.

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --ink: #011627;
  --porcelain: #fdfffc;
  --teal: #2ec4b6;
  --teal-ink: #14867c;
  --red: #e71d36;
  --red-ink: #d1102c;
  --amber: #ff9f1c;
  --amber-ink: #b06f0c;

  --bg-top: #f6f8f9;
  --bg-mid: #e9eef1;
  --bg-deep: #ccd6dc;

  --muted: #476070;
  --faint: #7b929e;
  --light-ink: #7d95a3;

  --line: rgba(1,22,39,0.07);
  --line-strong: rgba(1,22,39,0.12);
  --lift: 0 1px 2px rgba(1,22,39,0.05), 0 14px 30px -20px rgba(1,22,39,0.30);
  --lift-lg: 0 1px 2px rgba(1,22,39,0.05), 0 20px 44px -26px rgba(1,22,39,0.34);
  --r-card: 16px;
  --r-control: 10px;
}

.stApp {
  background: linear-gradient(180deg, var(--bg-top) 0%, var(--bg-mid) 46%, var(--bg-deep) 100%);
  background-attachment: fixed;
}

html, body, [class*="css"] {
  color: var(--ink);
  font-family: 'Outfit', system-ui, sans-serif;
}

/* -- Headings: geometric display type, no rules -- */
h1 {
  font-family: 'Outfit', sans-serif !important;
  font-weight: 600 !important;
  font-size: 2.6rem !important;
  letter-spacing: -0.035em;
  margin-bottom: 0.4rem !important;
  animation: rise 0.5s ease both;
}
h2, h3 {
  font-family: 'Outfit', sans-serif !important;
  font-weight: 600 !important;
  letter-spacing: -0.025em;
}
h2 { font-size: 1.6rem !important; }
h3 { font-size: 1.2rem !important; }

.eyebrow {
  display: block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--faint);
  animation: rise 0.4s ease both;
}

[data-testid="stCaptionContainer"] p {
  color: var(--muted) !important;
}

/* -- Divider: a hairline, not a printed rule -- */
hr {
  border: none !important;
  height: 0 !important;
  margin: 1.6rem 0 !important;
  border-top: 1px solid var(--line-strong) !important;
  box-shadow: none !important;
}

/* -- Sidebar: porcelain panel -- */
[data-testid="stSidebar"] {
  background: var(--porcelain);
  border-right: 1px solid var(--line);
}

/* -- File uploader: soft dashed intake slot -- */
[data-testid="stFileUploaderDropzone"] {
  background: rgba(253,255,252,0.58) !important;
  border: 1px dashed rgba(1,22,39,0.18) !important;
  border-radius: 12px !important;
}
[data-testid="stFileUploader"] section { border-radius: 12px !important; }

/* -- Buttons: 44px, soft radius, amber primary with ink text -- */
.stButton > button, .stDownloadButton > button {
  font-family: 'Outfit', sans-serif !important;
  font-weight: 500 !important;
  font-size: 0.9rem !important;
  min-height: 44px;
  border-radius: var(--r-control) !important;
  border: 1px solid var(--line) !important;
  background: var(--porcelain) !important;
  color: var(--ink) !important;
  box-shadow: 0 1px 2px rgba(1,22,39,0.05);
  transition: background 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  background: #ffffff !important;
  box-shadow: 0 1px 2px rgba(1,22,39,0.05), 0 10px 22px -12px rgba(1,22,39,0.35);
  transform: translateY(-1px);
}
.stButton > button[kind="primary"] {
  background: var(--amber) !important;
  border-color: transparent !important;
  color: var(--ink) !important;
  box-shadow: 0 10px 22px -10px rgba(255,159,28,0.9);
}
.stButton > button[kind="primary"]:hover {
  background: #ffab38 !important;
}
.stButton > button:disabled, .stButton > button:disabled:hover {
  background: rgba(1,22,39,0.04) !important;
  border-color: transparent !important;
  color: #a5b9c3 !important;
  box-shadow: none !important;
  transform: none;
}

/* -- Inputs -- */
[data-baseweb="input"], [data-baseweb="select"] > div, .stTextInput input {
  border-radius: var(--r-control) !important;
}

/* -- Metrics: floating porcelain stat cards -- */
[data-testid="stMetric"] {
  background: var(--porcelain);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.85rem 1rem;
  box-shadow: var(--lift);
}
[data-testid="stMetricLabel"] {
  font-family: 'Outfit', sans-serif !important;
  font-weight: 400 !important;
  font-size: 0.72rem !important;
  color: var(--faint) !important;
}
[data-testid="stMetricValue"] {
  font-family: 'IBM Plex Mono', monospace !important;
  font-weight: 500 !important;
  font-size: 1.3rem !important;
  color: var(--ink) !important;
}

/* -- Result cards -- */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--porcelain);
  border: 1px solid var(--line) !important;
  border-radius: var(--r-card) !important;
  box-shadow: var(--lift-lg);
  animation: rise 0.4s ease both;
}
[data-testid="stImage"] img {
  border-radius: 10px;
  border: 1px solid var(--line);
}

/* -- Label rows: field, value, hint; left-aligned, hairline separated -- */
.audit-panel { margin-top: 0.1rem; }
.audit-row {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--line);
}
.audit-field {
  font-family: 'Outfit', sans-serif;
  font-weight: 500;
  font-size: 0.92rem;
  min-width: 6.2rem;
  white-space: nowrap;
}
/* Kept as a small spacer: the dotted leader belonged to the panel
   aesthetic and reads as noise between porcelain cards. */
.audit-dots { flex: 0 0 0.1rem; }
.audit-value {
  font-family: 'IBM Plex Mono', monospace;
  font-weight: 600;
  white-space: nowrap;
}
.audit-value.flag { color: var(--red-ink); }
.audit-value .hint {
  font-family: 'Outfit', sans-serif;
  font-weight: 400;
  color: var(--muted);
  margin-left: 0.4rem;
}
.audit-item { border-bottom: 1px solid var(--line); }
.audit-item .audit-row { border-bottom: none; }
.audit-reason {
  font-size: 0.9rem;
  color: var(--muted);
  padding: 0 0 0.55rem 6.8rem;
  text-wrap: pretty;
}

/* -- Tabs: segmented control -- */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: 4px;
  padding: 4px;
  border-bottom: none;
  border-radius: 12px;
  background: rgba(1,22,39,0.05);
  width: max-content;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  font-family: 'Outfit', sans-serif !important;
  font-weight: 500;
  font-size: 0.88rem;
  min-height: 34px;
  border: none;
  border-radius: 9px;
  padding: 0.3rem 1rem;
  color: var(--muted);
}
[data-testid="stTabs"] [aria-selected="true"] {
  background: var(--porcelain);
  color: var(--ink) !important;
  box-shadow: 0 1px 2px rgba(1,22,39,0.08);
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { display: none; }

@keyframes rise {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
""", unsafe_allow_html=True)


def resolve_api_key() -> str:
    """Streamlit secrets first (cloud), then environment (local .env)."""
    try:
        if "OPENROUTER_API_KEY" in st.secrets:
            return str(st.secrets["OPENROUTER_API_KEY"]).strip()
    except Exception:
        pass  # No secrets.toml at all — fall through to the environment.
    import os

    from puppets.config import load_dotenv
    load_dotenv()
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def stage_uploads(uploads, directory: Path) -> list[Path]:
    """Write in-memory uploads to disk so the pipeline can read them as files."""
    paths = []
    for index, upload in enumerate(uploads, start=1):
        # Prefix keeps upload order stable and avoids collisions on same-named files.
        path = directory / f"{index:03d}_{Path(upload.name).name}"
        path.write_bytes(upload.getbuffer())
        paths.append(path)
    return paths


def label_list(result) -> str:
    """Render the label variables as a nutrition-facts-style audit panel.

    The raw 1/0/null is what ends up in labels.csv, so that is what is shown,
    with the plain-English reading as a hint. A field is flagged red only
    when its value is the thing the audit is trying to catch — see
    LABEL_IS_FINDING.
    """
    rows = []
    for field in LABEL_FIELDS:
        value = getattr(result, field)
        shown = "null" if value is None else str(value)
        hint = html.escape(LABEL_HINT[field][value])
        value_class = "audit-value flag" if LABEL_IS_FINDING[field][value] else "audit-value"
        reason = getattr(result, field + REASON_SUFFIX, None)
        reason_html = (
            f'<div class="audit-reason">{html.escape(reason)}</div>'
            if reason else ""
        )
        rows.append(
            f'<div class="audit-item">'
            f'<div class="audit-row">'
            f'<span class="audit-field">{html.escape(field)}</span>'
            f'<span class="audit-dots"></span>'
            f'<span class="{value_class}">{shown}'
            f'<span class="hint">— {hint}</span></span>'
            f'</div>'
            f'{reason_html}'
            f'</div>'
        )
    return f'<div class="audit-panel">{"".join(rows)}</div>'


def display_name(image_path: str) -> str:
    """Strip the staging prefix added by stage_uploads."""
    name = Path(image_path).name
    return name.split("_", 1)[1] if "_" in name[:4] else name


def codebook_variables() -> str | None:
    """The `## Variables` section of CODEBOOK.md, which is the source of truth.

    Sliced out rather than restated here so the app can never drift from the
    document the prompts are compiled from.
    """
    try:
        text = CODEBOOK_PATH.read_text(encoding="utf-8")
    except OSError:
        return None
    start = text.find("## Variables")
    if start == -1:
        return None
    end = text.find("\n---", start)
    return text[start:end if end != -1 else len(text)].strip()


def render_codebook() -> None:
    st.markdown(
        '<span class="eyebrow">SOCK-PUPPET AUDIT · PHASE 1 · UPF MARKETING</span>',
        unsafe_allow_html=True,
    )
    st.title("📖 Codebook")
    st.caption("What each labelled variable means. These definitions are the "
               "source of truth — the model's prompts are compiled from them.")

    section = codebook_variables()
    if section is None:
        st.warning(f"Could not read the variable definitions from "
                   f"`{CODEBOOK_PATH.name}`.")
        return
    st.markdown(section)
    st.caption("Full codebook — unit of analysis, general decision rules and "
               "adjudicated edge cases — lives in CODEBOOK.md.")


# --- The call cap -----------------------------------------------------
#
# MAX_CALLS is a courtesy limit per browser session, enforced two ways:
#
# 1. A pre-check before starting a run refuses anything estimated to exceed
#    the remaining budget, with a clear message — this is the honest UX,
#    since pipeline.run catches per-agent exceptions and records them as
#    per-unit errors, so a cap tripping mid-run would otherwise surface as
#    confusing, unrelated-looking failures.
# 2. A counting wrapper around the low-level API calls is a backstop that
#    raises if the pre-check estimate was wrong.
#
# pipeline.py does `from .openrouter import ... complete, transcribe` — a
# from-import — so patching puppets.openrouter.complete has no effect on
# calls made from inside pipeline.py. The names actually invoked live as
# puppets.pipeline.complete / puppets.pipeline.transcribe, and those are
# what must be rebound.
#
# pipeline.run uses a ThreadPoolExecutor, so the wrapper is invoked from
# worker threads — a threading.Lock protects the counter, and the counter
# itself is a plain object (not st.session_state, which is not reliably
# accessible off the ScriptRunContext thread) created on the main thread and
# stashed in st.session_state before the run starts.


class _CallBudget:
    def __init__(self, max_calls: int) -> None:
        self.max_calls = max_calls
        self.used = 0
        self._lock = threading.Lock()

    def remaining(self) -> int:
        with self._lock:
            return self.max_calls - self.used

    def charge(self, n: int = 1) -> None:
        with self._lock:
            if self.used + n > self.max_calls:
                self.used = self.max_calls
                raise RuntimeError(
                    f"Session call budget exceeded ({self.max_calls} calls).")
            self.used += n


def _install_call_cap_wrapper() -> None:
    """Rebind puppets.pipeline.complete/transcribe to count and cap calls.

    Guarded by a sentinel attribute so a Streamlit rerun does not wrap an
    already-wrapped function.
    """
    if getattr(pipeline, "_call_cap_installed", False):
        return

    real_complete = pipeline.complete
    real_transcribe = pipeline.transcribe

    def counted_complete(*args, **kwargs):
        budget = st.session_state.get("_call_budget")
        if budget is not None:
            budget.charge(1)
        return real_complete(*args, **kwargs)

    def counted_transcribe(*args, **kwargs):
        budget = st.session_state.get("_call_budget")
        if budget is not None:
            budget.charge(1)
        return real_transcribe(*args, **kwargs)

    pipeline.complete = counted_complete
    pipeline.transcribe = counted_transcribe
    pipeline._call_cap_installed = True


_install_call_cap_wrapper()

if "_call_budget" not in st.session_state:
    st.session_state["_call_budget"] = _CallBudget(MAX_CALLS)


def _estimate_calls(n_units: int, audio_escalation: bool) -> int:
    """Worst case: 3 calls/unit (agent flow), plus 2/unit if audio may fire."""
    return n_units * 3 + (2 if audio_escalation else 0)


# --- Sidebar: run settings -------------------------------------------------

with st.sidebar:
    st.header("Intake")

    st.caption(f"Model: `{DEFAULT_MODEL}`")

    api_key = resolve_api_key()
    if not api_key:
        api_key = st.text_input("OpenRouter API key", type="password").strip()
        st.caption("Set OPENROUTER_API_KEY in Secrets (cloud) or .env (local) "
                   "to skip this.")

    with st.expander("Per-agent models (agent flow only)"):
        st.caption("Used by the focused per-field agents, which make "
                   "one focused call per label. Leave a field blank to use "
                   f"the model above (`{DEFAULT_MODEL}`) for that agent.")
        ad_model_override = st.text_input(
            "Ad-detection model", value="", key="ad_model_override").strip()
        food_model_override = st.text_input(
            "Food-detection model", value="", key="food_model_override").strip()
        upf_model_override = st.text_input(
            "UPF-classification model", value="", key="upf_model_override").strip()

    st.divider()
    budget: _CallBudget = st.session_state["_call_budget"]
    st.metric("API calls remaining", f"{budget.remaining()} / {budget.max_calls}")
    st.caption("A courtesy limit per browser session — the real cap on spend "
               "is the credit limit on the OpenRouter key behind this app.")

# --- Tab 1: upload and label -----------------------------------------------


def render_labelling(api_key: str, ad_model: str, food_model: str, upf_model: str) -> None:
    st.markdown(
        '<span class="eyebrow">SOCK-PUPPET AUDIT · PHASE 1 · UPF MARKETING</span>',
        unsafe_allow_html=True,
    )
    st.title("🧪 Screenshot labelling")
    st.caption("Sock-puppet audit MVP — labels each screenshot for advertising, "
               "food presence, and ultra-processed food (NOVA 4).")

    uploads = st.file_uploader(
        "Upload screenshots",
        type=[s.lstrip(".") for s in sorted(SUPPORTED_SUFFIXES)],
        accept_multiple_files=True,
    )

    if uploads:
        st.caption(f"{len(uploads)} image(s) will be labelled together as one video.")

    st.caption(AGENT_MODE_CAPTION)

    rationale = st.checkbox(
        "Ask the model to justify each label",
        key="labelling_rationale",
        help="Adds a one-sentence reason per label, shown with the results and "
             "written to the CSV. Costs roughly a fifth more per run.",
    )

    audio_upload = st.file_uploader(
        "Video audio (optional)",
        type=[s.lstrip(".") for s in sorted(AUDIO_SUFFIXES)],
        accept_multiple_files=False,
        help="The audio of the same video these frames came from. Used "
             "only when the frames and metadata show no ad.",
    )
    audio_escalation = st.checkbox(
        "Check the audio when no ad is found",
        key="labelling_audio_escalation",
        disabled=audio_upload is None,
        help="Transcribes the audio and judges whether the speech "
             "discloses a paid promotion — the case where a sponsorship "
             "is only ever spoken. Adds 2 calls per unit that has no ad "
             "in frame; can only turn is_ad from 0 to 1, never back.",
    )
    if audio_upload is None:
        st.caption("Attach audio to enable the spoken-disclosure check.")

    go = st.button("Run labelling", type="primary",
                   disabled=not uploads or not api_key, width="stretch")

    if go:
        budget: _CallBudget = st.session_state["_call_budget"]
        escalation_armed = audio_escalation and audio_upload is not None
        estimate = _estimate_calls(1, escalation_armed)
        if estimate > budget.remaining():
            st.error(
                f"This run could take up to {estimate} API call(s), but only "
                f"{budget.remaining()} remain in this session's budget of "
                f"{budget.max_calls}. Start a new session, or turn off audio "
                f"escalation to reduce the estimate."
            )
            return
        cfg = Config(api_key=api_key, model=DEFAULT_MODEL, mode=DEFAULT_MODE,
                     temperature=0.0, max_workers=1, timeout=120, max_retries=3,
                     ad_model=ad_model, food_model=food_model, upf_model=upf_model,
                     rationale=rationale,
                     audio_escalation=escalation_armed)
        with tempfile.TemporaryDirectory() as staging:
            paths = stage_uploads(uploads, Path(staging))
            audio_path = None
            if cfg.audio_escalation:
                audio_path = Path(staging) / audio_upload.name
                audio_path.write_bytes(audio_upload.getbuffer())
            with st.spinner(f"Labelling {len(paths)} image(s)…"):
                logger.info("starting labelling run: 1 bundle, model=%s", cfg.model)
                start = time.monotonic()
                try:
                    results, summary = run(
                        cfg, [Bundle(images=paths, audio=audio_path)])
                except RuntimeError as exc:
                    st.error(str(exc))
                    return
                elapsed = time.monotonic() - start
                logger.info(
                    "labelling run finished in %.1fs, %d error(s)",
                    elapsed, summary.n_errors,
                )
            # Read image bytes now — the staging directory disappears on exit.
            thumbnails = {str(p): p.read_bytes() for p in paths}
        # cfg is local to this branch, but the panel below re-renders from
        # session state on every later rerun — so whether escalation was
        # armed has to travel with the results, not be read off cfg.
        st.session_state["run"] = (results, summary, thumbnails,
                                   cfg.audio_escalation)

    if "run" not in st.session_state:
        return

    results, summary, thumbnails, ran_with_audio = st.session_state["run"]

    st.divider()
    st.subheader("Results")

    if summary.n_errors:
        st.warning(f"{summary.n_errors} of {summary.n_label_sets} label set(s) failed.")

    cols = st.columns(5)
    cols[0].metric("Total cost", f"${summary.total_cost_usd:.6f}")
    cols[1].metric("Cost per image", f"${summary.mean_cost_per_image_usd:.6f}")
    cols[2].metric("Cost per API call", f"${summary.mean_cost_per_call_usd:.6f}",
                   help="Agent flow makes 2-3 API calls per unit, so this is "
                        "not the same as cost per image.")
    cols[3].metric("API calls", f"{summary.n_api_calls:,}")
    cols[4].metric("Tokens", f"{summary.total_prompt_tokens:,} in / "
                             f"{summary.total_completion_tokens:,} out")
    # Only shown when the audio channel actually ran, so a normal run's
    # results panel is unchanged.
    if summary.n_escalations:
        flips = sum(1 for r in results if r.audio_is_ad == 1)
        st.caption(
            f"{summary.n_escalations} unit(s) had no ad in frame or metadata "
            f"and were checked against the audio, at "
            f"${summary.audio_cost_usd:.6f} of the total. "
            f"{flips} were flipped to is_ad = 1 by what was said."
        )
    elif ran_with_audio:
        # Escalation was armed and never fired. Silence here would read as
        # "the audio agreed", which is not what happened.
        st.caption(
            "The audio was never checked: every unit already had an ad in "
            "frame or metadata, so nothing reached the escalation trigger."
        )
    audio_errors = [r for r in results if r.audio_error]
    if audio_errors:
        st.caption(
            f"{len(audio_errors)} unit(s) could not be checked against the "
            f"audio: {audio_errors[0].audio_error}. Their other labels are "
            f"unaffected."
        )

    if summary.n_label_sets and summary.n_api_calls != summary.n_label_sets:
        st.caption(f"{summary.n_label_sets} unit(s) labelled via "
                   f"{summary.n_api_calls} API call(s) — "
                   f"{summary.n_api_calls / summary.n_label_sets:.1f} call(s) per unit.")

    for i, result in enumerate(results, start=1):
        with st.container(border=True):
            st.markdown(
                f'<span class="eyebrow">EXHIBIT {i:02d} · {html.escape(result.bundle_id)}</span>',
                unsafe_allow_html=True,
            )
            left, right = st.columns([1, 2])
            with left:
                thumb_cols = st.columns(min(len(result.image_paths), 5) or 1)
                for j, image_path in enumerate(result.image_paths):
                    thumb_cols[j % len(thumb_cols)].image(
                        thumbnails[image_path],
                        caption=display_name(image_path),
                        width="stretch",
                    )
            with right:
                if result.error:
                    st.error(result.error)
                else:
                    st.markdown(label_list(result), unsafe_allow_html=True)
                st.caption(
                    f"${result.cost_usd:.6f} · {result.n_images} frame(s) · "
                    f"{result.prompt_tokens:,} in / {result.completion_tokens:,} out"
                )

    st.divider()
    st.subheader("Download")
    st.caption("Nothing is stored server-side — download anything you want to keep.")
    d1, d2, d3 = st.columns(3)
    d1.download_button("labels.csv", labels_csv(results),
                       file_name=f"{summary.run_id}_labels.csv", mime="text/csv",
                       width="stretch")
    d2.download_button("raw.jsonl", raw_jsonl(results),
                       file_name=f"{summary.run_id}_raw.jsonl", mime="application/json",
                       width="stretch")
    d3.download_button("summary.json", summary_json(summary),
                       file_name=f"{summary.run_id}_summary.json",
                       mime="application/json", width="stretch")


# --- Layout ----------------------------------------------------------------

tab_labelling, tab_codebook = st.tabs(["Labelling", "Codebook"])
with tab_labelling:
    render_labelling(api_key, ad_model_override, food_model_override, upf_model_override)
with tab_codebook:
    render_codebook()
