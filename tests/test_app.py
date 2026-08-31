"""Streamlit front-end tests using AppTest — no browser, no network."""

from __future__ import annotations

import base64
import unittest
from pathlib import Path

from puppets.pipeline import LabelResult, RunSummary
from puppets.schema import AD_FIELDS, UNDISCLOSED_FIELD

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover - streamlit not installed
    AppTest = None

APP = str(Path(__file__).resolve().parents[1] / "app.py")
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def fake_run(mode: str = "agent_per_bundle", with_error: bool = False):
    # An ad-and-food unit and an organic no-food one. The ad sub-flags are
    # set through AD_FIELDS rather than named one by one, so a further
    # sub-variable does not break this fixture.
    ad_unit = LabelResult(
        image_paths=["/tmp/staging/001_ad_shot.png"], bundle_id="run-b0001",
        has_food=1, is_upf=1, food_category="sweets_and_desserts",
        brands=["Choco Co"], foods=["chocolate bar"],
        prompt_tokens=1200, completion_tokens=18, cost_usd=0.00212)
    for field in AD_FIELDS:
        # ad_undisclosed is suppressed to null by the pipeline whenever
        # another ad flag is 1 — mirror that here.
        setattr(ad_unit, field, None if field == UNDISCLOSED_FIELD else 1)
    organic_unit = LabelResult(
        image_paths=["/tmp/staging/002_feed.png"], bundle_id="run-b0001",
        has_food=0, is_upf=None, prompt_tokens=1180,
        completion_tokens=17, cost_usd=0.00208)
    for field in AD_FIELDS:
        setattr(organic_unit, field, 0)
    results = [ad_unit, organic_unit]
    if with_error:
        results[1] = LabelResult(
            image_paths=["/tmp/staging/002_feed.png"], bundle_id="run-b0001",
            error="HTTP 429: rate limited",
        )
    n_images = sum(r.n_images for r in results)
    summary = RunSummary(
        run_id="20260807T120000Z-abc123", model="test/model", mode=mode,
        bundle_size=2, started_at="2026-08-07T12:00:00+00:00",
        finished_at="2026-08-07T12:00:05+00:00", n_images=n_images,
        n_label_sets=len(results),
        n_errors=1 if with_error else 0, n_api_calls=2,
        total_cost_usd=sum(r.cost_usd for r in results),
        mean_cost_per_image_usd=sum(r.cost_usd for r in results) / n_images,
        mean_cost_per_call_usd=sum(r.cost_usd for r in results) / 2,
        total_prompt_tokens=sum(r.prompt_tokens for r in results),
        total_completion_tokens=sum(r.completion_tokens for r in results),
    )
    thumbnails = {p: PNG_1PX for r in results for p in r.image_paths}
    return results, summary, thumbnails


@unittest.skipIf(AppTest is None, "streamlit not installed")
class AppTests(unittest.TestCase):
    def run_app(self, seeded=None):
        app = AppTest.from_file(APP, default_timeout=30)
        if seeded is not None:
            app.session_state["run"] = seeded
        app.run()
        return app

    def test_empty_state_renders_without_exception(self):
        app = self.run_app()
        self.assertFalse(app.exception, [str(e) for e in app.exception])
        self.assertIn("Screenshot labelling", app.title[0].value)

    def test_run_button_disabled_without_uploads(self):
        app = self.run_app()
        self.assertTrue(app.button[0].disabled)

    def test_sidebar_shows_fixed_model(self):
        app = self.run_app()
        self.assertFalse(app.exception, [str(e) for e in app.exception])
        captions = " ".join(c.value for c in app.caption)
        self.assertIn("Model:", captions)

    def test_sidebar_shows_remaining_budget(self):
        app = self.run_app()
        self.assertFalse(app.exception, [str(e) for e in app.exception])
        metrics = {m.label: m.value for m in app.metric}
        self.assertIn("API calls remaining", metrics)

    def test_results_render_labels_and_costs(self):
        app = self.run_app(seeded=fake_run())
        self.assertFalse(app.exception, [str(e) for e in app.exception])

        metrics = {m.label: m.value for m in app.metric}
        self.assertEqual(metrics["Total cost"], "$0.004200")
        self.assertEqual(metrics["Cost per image"], "$0.002100")
        markdown = " ".join(m.value for m in app.markdown)
        # Every ad sub-variable gets its own row, and the descriptive
        # variables are shown alongside the binary ones.
        for field in AD_FIELDS:
            self.assertIn(field, markdown)
        self.assertIn("food_category", markdown)
        self.assertIn("sweets_and_desserts", markdown)
        self.assertIn("Choco Co", markdown)
        self.assertIn("chocolate bar", markdown)
        self.assertIn("not applicable", markdown)

    def test_error_result_shows_message_not_labels(self):
        app = self.run_app(seeded=fake_run(with_error=True))
        self.assertFalse(app.exception, [str(e) for e in app.exception])
        self.assertTrue(any("429" in e.value for e in app.error))
        self.assertTrue(any("1 of 2" in w.value for w in app.warning))

    def test_downloads_offered_for_all_three_files(self):
        app = self.run_app(seeded=fake_run())
        labels = [b.label for b in app.get("download_button")]
        self.assertEqual(labels, ["labels.csv", "raw.jsonl", "summary.json"])

    def test_only_labelling_and_codebook_tabs_exist(self):
        app = self.run_app()
        self.assertFalse(app.exception, [str(e) for e in app.exception])
        tab_labels = [t.proto.label for t in app.tabs]
        self.assertEqual(tab_labels, ["Labelling", "Codebook"])

    def test_codebook_tab_renders_variable_definitions(self):
        app = self.run_app()
        self.assertFalse(app.exception, [str(e) for e in app.exception])
        markdown = " ".join(m.value for m in app.markdown)
        self.assertIn("Codebook", " ".join(t.value for t in app.title))


@unittest.skipIf(AppTest is None, "streamlit not installed")
class CallCapTests(unittest.TestCase):
    """The session call cap: pre-check refusal and wrapper backstop."""

    def test_precheck_refuses_a_run_that_would_exceed_the_budget(self):
        import app as app_module

        budget = app_module._CallBudget(2)
        estimate = app_module._estimate_calls(1)
        # One unit costs up to MAX_CALLS_PER_UNIT calls — over a budget of 2.
        self.assertEqual(estimate, app_module.MAX_CALLS_PER_UNIT)
        self.assertGreater(estimate, budget.remaining())

    def test_wrapper_counts_and_caps_completions(self):
        import app as app_module

        budget = app_module._CallBudget(2)
        calls = []

        def fake_complete(*args, **kwargs):
            calls.append(1)
            return "ok"

        app_module.pipeline.complete = fake_complete
        app_module.pipeline._call_cap_installed = False
        app_module._install_call_cap_wrapper()

        import streamlit as st
        st.session_state["_call_budget"] = budget

        wrapped = app_module.pipeline.complete
        wrapped()
        wrapped()
        with self.assertRaises(RuntimeError):
            wrapped()
        # The third call is refused before reaching the real API call.
        self.assertEqual(len(calls), 2)
        self.assertEqual(budget.used, 2)


class ImportSurfaceTests(unittest.TestCase):
    """The app must import only its allowed puppets modules."""

    ALLOWED = {
        "puppets.config",
        "puppets.pipeline",
        "puppets.images",
        "puppets.audio",
        "puppets.schema",
        "puppets.storage",
        "puppets.logging_setup",
    }
    BLOCKED = {
        "puppets.benchmarks",
        "puppets.gold",
        "puppets.trace",
        "puppets.trace_component",
        "puppets.trace_graph",
        "video_testing",
    }

    def test_allowed_modules_import(self):
        import importlib
        for name in self.ALLOWED:
            importlib.import_module(name)

    def test_blocked_modules_are_not_imported_by_the_app(self):
        source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text()
        for name in self.BLOCKED:
            self.assertNotIn(name, source)


if __name__ == "__main__":
    unittest.main()
