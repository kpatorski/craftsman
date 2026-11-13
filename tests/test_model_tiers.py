"""Tests for the model tiers -- see EXECUTION.md, "Choosing a model". craftsman names work by tier (fast, balanced,
deep), never by model; the developer maps each tier to a model, and the defaults live in one place.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import model_tiers  # noqa: E402


class TiersCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name) / "home"
        self.claude = pathlib.Path(self.tmp.name) / "claude"
        self.saved = {key: os.environ.get(key) for key in ("CRAFTSMAN_HOME", "CLAUDE_CONFIG_DIR")}
        os.environ.update(CRAFTSMAN_HOME=str(self.home), CLAUDE_CONFIG_DIR=str(self.claude))

    def tearDown(self):
        for key, value in self.saved.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
        self.tmp.cleanup()

    def settings(self, **values):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "settings.json").write_text(json.dumps(values))


class TierMappingTest(TiersCase):
    def test_every_tier_has_a_model_before_the_developer_chooses_any(self):
        self.assertEqual(model_tiers.models(), {"fast": "haiku", "balanced": "sonnet", "deep": "opus"})

    def test_the_developer_maps_a_tier_to_another_model(self):
        self.settings(models={"deep": "claude-opus-9-1", "fast": "sonnet"})
        self.assertEqual(model_tiers.model("deep"), "claude-opus-9-1")
        self.assertEqual(model_tiers.model("fast"), "sonnet")
        self.assertEqual(model_tiers.model("balanced"), "sonnet")

    def test_a_blank_or_broken_entry_falls_back_to_the_default(self):
        self.settings(models={"deep": "  ", "fast": 7})
        self.assertEqual((model_tiers.model("deep"), model_tiers.model("fast")), ("opus", "haiku"))
        self.settings(models="opus")
        self.assertEqual(model_tiers.model("deep"), "opus")

    def test_a_tier_is_set_and_an_empty_model_brings_the_default_back(self):
        self.settings(theme="paper")
        model_tiers.set_model("balanced", " claude-sonnet-9-0[1m] ")
        self.assertEqual(model_tiers.model("balanced"), "claude-sonnet-9-0[1m]")
        model_tiers.set_model("balanced", "")
        self.assertEqual(model_tiers.model("balanced"), "sonnet")
        self.assertEqual(json.loads((self.home / "settings.json").read_text())["theme"], "paper")

    def test_an_unknown_tier_or_a_model_name_with_spaces_is_refused(self):
        for tier, model in (("cheap", "haiku"), ("deep", "opus please"), ("deep", "opus;rm"), ("deep", None)):
            with self.subTest(tier=tier, model=model):
                with self.assertRaises(ValueError):
                    model_tiers.set_model(tier, model)
        self.assertFalse((self.home / "settings.json").exists())

    def test_a_model_belongs_to_the_tier_it_is_mapped_to(self):
        self.settings(models={"deep": "claude-opus-9-1"})
        self.assertEqual(model_tiers.tier_of("haiku"), "fast")
        self.assertEqual(model_tiers.tier_of("claude-opus-9-1"), "deep")
        self.assertEqual(model_tiers.tier_of("opus"), "deep", "a subagent takes the alias of a model mapped by id")
        self.assertIsNone(model_tiers.tier_of("fable"))

    def test_the_mapping_reads_as_one_line(self):
        self.assertEqual(model_tiers.described(), "fast = haiku, balanced = sonnet, deep = opus")
        done = subprocess.run([sys.executable, str(SCRIPTS / "model_tiers.py")], capture_output=True, text=True,
                              env=dict(os.environ), check=True)
        self.assertEqual(done.stdout.strip(), "fast = haiku, balanced = sonnet, deep = opus")


class SuggestionsTest(TiersCase):
    def test_the_models_claude_code_offers_are_suggested(self):
        self.assertEqual(model_tiers.suggestions(), ["haiku", "sonnet", "opus", "fable"])

    def test_a_lineup_the_developer_set_for_claude_code_is_suggested_instead(self):
        self.claude.mkdir()
        (self.claude / "settings.json").write_text(json.dumps({"availableModels": ["sonnet", "claude-opus-9-1"]}))
        self.assertEqual(model_tiers.suggestions(), ["sonnet", "claude-opus-9-1"])


class ModelsEndpointTest(TiersCase):
    """The dashboard's Manage view maps the tiers through the server."""

    def setUp(self):
        super().setUp()
        import dashboard_server
        self.server = dashboard_server.ThreadingHTTPServer(("127.0.0.1", 0), dashboard_server.Handler)
        self.port = self.server.server_address[1]
        dashboard_server.Handler.hub = dashboard_server.Hub(self.home / "content", [], self.port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, body=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=None if body is None else json.dumps(body).encode(),
            method="GET" if body is None else "POST",
            headers={"Host": f"127.0.0.1:{self.port}", "X-Craftsman": "1", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_the_page_gets_each_tier_its_model_its_default_and_the_suggestions(self):
        status, answer = self.call("/api/models")
        self.assertEqual(status, 200)
        self.assertEqual([(t["id"], t["model"], t["default"]) for t in answer["tiers"]],
                         [("fast", "haiku", "haiku"), ("balanced", "sonnet", "sonnet"), ("deep", "opus", "opus")])
        self.assertTrue(all(t["says"] for t in answer["tiers"]))
        self.assertEqual(answer["suggestions"], ["haiku", "sonnet", "opus", "fable"])

    def test_the_page_maps_a_tier_and_a_wrong_one_changes_nothing(self):
        status, answer = self.call("/api/models", {"tier": "deep", "model": "sonnet"})
        self.assertEqual(status, 200)
        self.assertEqual(answer["tiers"][2]["model"], "sonnet")
        self.assertEqual(self.call("/api/models", {"tier": "deep", "model": "two words"})[0], 400)
        self.assertEqual(self.call("/api/models", {"tier": "huge", "model": "opus"})[0], 400)
        self.assertEqual(model_tiers.model("deep"), "sonnet")


if __name__ == "__main__":
    unittest.main()
