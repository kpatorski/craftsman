"""Tests for the review page's dictation client: `makeDictation` records with the browser's microphone and sends the
recording to the dashboard, `joinDictated` fits the text in at the caret. Both are taken out of review_page.html and
run in Node with fakes for the microphone, MediaRecorder, the clock and the upload -- see REVIEW.md, "Dictation".

Run: python3 -m unittest discover -s tests
"""
import json
import pathlib
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_review_page import NODE, PAGE, constant, function  # noqa: E402

# A scripted world: `script` runs against `d` (the dictation), `w` (the fakes) and `log`, and returns what to check.
WORLD = r"""
const log = [];
const w = {
  denied: null, opus: true, peak: 0.4, answers: [], clock: 0, timers: [], tracksStopped: 0, posts: [], warmed: 0, texts: [],
};
class FakeRecorder {
  static isTypeSupported(type) { log.push("type " + type); return w.opus === true || w.opus === type; }
  constructor(stream, options) { this.state = "inactive"; this.options = options; w.recorder = this; }
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; this.ondataavailable({ data: { size: 3 } }); this.onstop(); }
}
const env = {
  media: { getUserMedia: async () => { if (w.denied) { const e = new Error("no"); e.name = w.denied; throw e; }
    return { getTracks: () => [{ stop: () => w.tracksStopped++ }] }; } },
  Recorder: FakeRecorder,
  Blob: class { constructor(parts, opts) { this.parts = parts; this.type = opts.type; w.blobType = opts.type; } },
  now: () => w.clock,
  setTimeout: (fn, ms) => { const t = { fn, at: w.clock + ms }; w.timers.push(t); return t; },
  clearTimeout: t => { w.timers = w.timers.filter(x => x !== t); },
  meter: () => () => w.peak,
  post: async (url, blob) => { w.posts.push(url); const a = w.answers.shift() || { status: 200, body: { text: "Rename it" } };
    if (a.throws) throw new Error("down"); return a; },
  warm: () => w.warmed++,
  onState: (state, info) => log.push(state + (info && info.kind ? ":" + info.kind : "") + (info && info.note ? " (" + info.note + ")" : "")),
  onText: (text, target) => w.texts.push([text, target]),
};
const tick = async ms => { w.clock += ms; const due = w.timers.filter(t => t.at <= w.clock); w.timers = w.timers.filter(t => t.at > w.clock);
  for (const t of due) t.fn(); await new Promise(r => setImmediate(r)); };
const settle = () => new Promise(r => setImmediate(r));
const d = makeDictation(env);
(async () => {
  const out = await (async () => { SCRIPT })();
  console.log(JSON.stringify({ out, log, posts: w.posts, texts: w.texts, tracksStopped: w.tracksStopped, warmed: w.warmed,
    state: d.state(), active: d.active(), timers: w.timers.length }));
})();
"""


def world(script, **fakes):
    setup = "".join(f"w.{key} = {json.dumps(value)};" for key, value in fakes.items())
    program = function("makeDictation") + WORLD.replace("SCRIPT", setup + script)
    result = subprocess.run([NODE, "-e", program], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class DictationClientTest(unittest.TestCase):
    def test_a_recording_is_sent_and_its_text_goes_to_the_field_it_was_started_in(self):
        r = world("""await d.start("draft-box", "pl"); await tick(3000); d.stop(); await settle(); await settle();""")
        self.assertEqual(r["posts"], ["/api/dictate?language=pl"])
        self.assertEqual(r["texts"], [["Rename it", "draft-box"]])
        self.assertEqual([s for s in r["log"] if not s.startswith("type")], ["asking", "recording", "transcribing", "idle"])
        self.assertEqual((r["tracksStopped"], r["state"], r["timers"]), (1, "idle", 0))
        self.assertIn("type audio/webm;codecs=opus", r["log"])
        self.assertEqual(r["warmed"], 1, "the engine is warmed up while the developer speaks")

    def test_a_denied_microphone_is_explained_and_nothing_is_recorded(self):
        r = world("""return await d.start("ask-in", "en");""", denied="NotAllowedError")
        self.assertEqual(r["out"], False)
        self.assertIn("error:permission", r["log"])
        self.assertEqual((r["posts"], r["state"]), ([], "error"))

    def test_a_browser_that_records_opus_only_in_ogg_records_ogg(self):
        r = world("""await d.start("ask-in", "en"); await tick(3000); d.stop(); await settle(); await settle();
                     return [w.recorder.options.mimeType, w.blobType];""", opus="audio/ogg;codecs=opus")
        self.assertEqual(r["out"], ["audio/ogg;codecs=opus", "audio/ogg"])
        self.assertEqual(r["texts"], [["Rename it", "ask-in"]])

    def test_a_browser_that_cannot_record_opus_is_told_so_before_asking_for_the_microphone(self):
        r = world("""return await d.start("ask-in", "en");""", opus=False)
        self.assertIn("error:format", r["log"])
        self.assertNotIn("asking", r["log"])

    def test_the_recording_stops_by_itself_just_under_a_minute(self):
        r = world("""await d.start("ask-in", "en"); await tick(58000); const before = d.state(); await tick(1000);
                     await settle(); return before;""")
        self.assertEqual(r["out"], "recording")
        self.assertEqual(r["posts"], ["/api/dictate?language=en"])

    def test_a_cancelled_recording_is_discarded_and_the_microphone_released(self):
        r = world("""await d.start("ask-in", "en"); await tick(2000); d.cancel(); await settle();""")
        self.assertEqual(r["posts"], [])
        self.assertEqual((r["tracksStopped"], r["state"], r["timers"]), (1, "idle", 0))

    def test_a_cancel_while_the_browser_asks_for_the_microphone_records_nothing(self):
        r = world("""const started = d.start("ask-in", "en"); d.cancel(); await started; return d.state();""")
        self.assertEqual(r["out"], "idle")
        self.assertNotIn("recording", r["log"])
        self.assertEqual(r["tracksStopped"], 1)

    def test_a_too_short_or_silent_recording_is_not_sent(self):
        short = world("""await d.start("ask-in", "en"); await tick(200); d.stop(); await settle();""")
        silent = world("""await d.start("ask-in", "en"); await tick(3000); d.stop(); await settle();""", peak=0.001)
        for r in (short, silent):
            self.assertEqual(r["posts"], [])
            self.assertEqual(r["state"], "idle")
        self.assertTrue(any("Nothing was heard" in s for s in silent["log"]))

    def test_a_busy_engine_is_tried_once_more_then_reported(self):
        once = world("""await d.start("ask-in", "en"); await tick(3000); d.stop(); await settle(); await tick(1500); await settle();""",
                     answers=[{"status": 429, "body": {"kind": "busy"}}])
        twice = world("""await d.start("ask-in", "en"); await tick(3000); d.stop(); await settle(); await tick(1500); await settle();""",
                      answers=[{"status": 429, "body": {"kind": "busy"}}, {"status": 429, "body": {"kind": "busy", "error": "busy"}}])
        self.assertEqual((len(once["posts"]), once["texts"]), (2, [["Rename it", "ask-in"]]))
        self.assertEqual(len(twice["posts"]), 2)
        self.assertIn("error:busy", twice["log"])

    def test_a_failed_or_unreachable_engine_is_an_error_the_developer_can_retry_from(self):
        failed = world("""await d.start("ask-in", "en"); await tick(3000); d.stop(); await settle(); await settle();
                          return await d.start("ask-in", "en");""",
                       answers=[{"status": 409, "body": {"kind": "not-set-up", "error": "Run /craftsman:dictation setup"}}])
        down = world("""await d.start("ask-in", "en"); await tick(3000); d.stop(); await settle(); await settle();""",
                     answers=[{"throws": True}])
        self.assertIn("error:not-set-up", failed["log"])
        self.assertEqual(failed["out"], True, "a new recording can start after an error")
        self.assertIn("error:unreachable", down["log"])

    def test_a_second_start_while_recording_is_ignored(self):
        r = world("""await d.start("ask-in", "en"); return await d.start("draft-box", "en");""")
        self.assertEqual(r["out"], False)
        self.assertEqual((r["state"], r["active"]), ("recording", True))


def join(before, text, after):
    program = function("joinDictated") + f"\nconsole.log(JSON.stringify(joinDictated(...{json.dumps([before, text, after])})));"
    return json.loads(subprocess.run([NODE, "-e", program], capture_output=True, text=True, check=True).stdout)


@unittest.skipUnless(NODE, "node is not installed")
class JoinDictatedTest(unittest.TestCase):
    def test_dictated_text_gets_a_space_from_the_words_around_it(self):
        self.assertEqual(join("Split the", " class ", "into two"), " class ")
        self.assertEqual(join("Split the ", "class", " into two"), "class")

    def test_at_the_start_of_an_empty_field_it_goes_in_as_spoken(self):
        self.assertEqual(join("", " Rename it. ", ""), "Rename it.")

    def test_no_space_goes_before_punctuation_that_follows(self):
        self.assertEqual(join("Split", "the class", ", then test"), " the class")

    def test_after_a_new_line_no_space_is_added(self):
        self.assertEqual(join("First point.\n", "second point", ""), "second point")


@unittest.skipUnless(NODE, "node is not installed")
class DictableFieldsTest(unittest.TestCase):
    def test_the_fields_for_prose_take_dictation_and_the_others_do_not(self):
        page = PAGE.read_text()
        self.assertIn("data-no-dictation", constant("DICTABLE"))
        for field in ('id="tree-search"', 'id="nr-path"', 'id="nr-url"', 'id="nr-target"', 'id="nr-source"',
                      'id="perm-rule-${id}"'):
            with self.subTest(field=field):
                self.assertRegex(page, field.replace("$", r"\$").replace("{", r"\{").replace("}", r"\}") + r"[^>]*data-no-dictation")


@unittest.skipUnless(NODE, "node is not installed")
class DictationOnThePageTest(unittest.TestCase):
    def test_a_box_being_dictated_into_is_not_redrawn_and_esc_cancels_first(self):
        self.assertIn("dictation.active()", function("busy"))
        self.assertIn("if (dictation && dictation.active()) return dictation.cancel();", function("onEscape").splitlines()[1])
        self.assertIn("placeMic();", function("render"))

    def test_the_setup_question_names_the_model_and_the_size_the_server_offers(self):
        setup = function("micSetup", prefix="async ")
        for fixed in ("0.7 GB", "Whisper small"):
            self.assertNotIn(fixed, setup)
        self.assertIn("offer.model", setup)
        self.assertIn("offer.download", setup)

    def test_the_setup_button_is_a_small_one_named_without_an_ellipsis(self):
        toggle = function("micToggle")
        self.assertIn('<button class="btn sm mic-setup" data-mic-setup>Set up</button>', toggle)
        self.assertNotIn("Set up…", toggle)
        self.assertRegex(PAGE.read_text(), r"\.mic-dock \.mic-say \.mic-setup \{[^}]*font-size: \.6875rem")

    def test_a_message_has_room_for_a_setup_sentence(self):
        self.assertRegex(PAGE.read_text(), r"\.mic-dock \.mic-say \{[^}]*max-width: 560px")

    def test_the_button_keeps_the_caret_in_the_box_and_the_page_talks_only_to_its_own_server(self):
        page = PAGE.read_text()
        self.assertIn('getElementById("mic").addEventListener("mousedown", e => e.preventDefault())', page)
        self.assertIn("<meta http-equiv=\"Content-Security-Policy\" content=\"connect-src 'self'\">", page)
        self.assertIn('<button class="mic-btn" id="mic-btn" type="button" aria-label="Dictate" aria-pressed="false"', page)


if __name__ == "__main__":
    unittest.main()
