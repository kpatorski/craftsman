"""Tests for whisper_convert.py, which turns OpenAI's Whisper checkpoint and tokenizer into the model the dictation
engine reads -- see REVIEW.md, "Dictation". The script runs with the dictation engine's Python (numpy, ctranslate2,
tokenizers): these tests use the one CRAFTSMAN_DICTATION_PYTHON names, else the engine set up in ~/.craftsman, and are
skipped when there is neither.

Run: python3 -m unittest discover -s tests
"""
import base64
import collections
import io
import json
import os
import pathlib
import pickle
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"


def engine_python():
    named = os.environ.get("CRAFTSMAN_DICTATION_PYTHON")
    found = pathlib.Path(named) if named else pathlib.Path.home() / ".craftsman" / "dictation" / "venv" / "bin" / "python"
    if not found.is_file():
        return None
    ok = subprocess.run([str(found), "-c", "import numpy, ctranslate2, tokenizers"], capture_output=True).returncode
    return str(found) if ok == 0 else None


PYTHON = engine_python()


def run(script, *args):
    program = f"import json, sys; sys.path.insert(0, {str(SCRIPTS)!r}); import whisper_convert as w\n{script}"
    done = subprocess.run([PYTHON, "-I", "-B", "-c", program, *args], capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


def torch_zip(path, obj, storages):
    """Write `obj` the way torch.save does -- a pickle in a zip, each tensor's data a raw file beside it -- without
    torch: stand-ins for the torch names the pickle refers to are put in sys.modules while it is written."""
    torch, utils = types.ModuleType("torch"), types.ModuleType("torch._utils")

    class HalfStorage:
        pass

    def _rebuild_tensor_v2(*args):
        pass

    HalfStorage.__module__, _rebuild_tensor_v2.__module__ = "torch", "torch._utils"
    HalfStorage.__qualname__, _rebuild_tensor_v2.__qualname__ = "HalfStorage", "_rebuild_tensor_v2"
    torch.HalfStorage, utils._rebuild_tensor_v2 = HalfStorage, _rebuild_tensor_v2
    saved = {name: sys.modules.get(name) for name in ("torch", "torch._utils")}
    sys.modules.update({"torch": torch, "torch._utils": utils})

    class Tensor:
        def __init__(self, key, shape, stride):
            self.key, self.shape, self.stride = key, shape, stride

        def __reduce__(self):
            return _rebuild_tensor_v2, (("storage", self.key), 0, self.shape, self.stride, False,
                                        collections.OrderedDict())

    class Pickler(pickle.Pickler):
        def persistent_id(self, item):
            if isinstance(item, tuple) and item[:1] == ("storage",):
                return ("storage", HalfStorage, item[1], "cpu", len(storages[item[1]]))
            return None

    try:
        raw = io.BytesIO()
        Pickler(raw, protocol=2).dump(obj(Tensor))
    finally:
        for name, module in saved.items():
            sys.modules.pop(name) if module is None else sys.modules.__setitem__(name, module)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("archive/data.pkl", raw.getvalue())
        for key, values in storages.items():
            archive.writestr(f"archive/data/{key}", struct.pack(f"<{len(values)}e", *values))


@unittest.skipUnless(PYTHON, "the dictation engine's Python is not available")
class CheckpointTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = pathlib.Path(self.tmp.name) / "model.pt"

    def test_the_checkpoint_is_read_without_torch_tensors_with_their_shape_and_layout(self):
        torch_zip(self.path, lambda Tensor: {"dims": {"n_vocab": 51865}, "model_state_dict": collections.OrderedDict(
            [("w", Tensor("0", (2, 3), (3, 1))), ("w_t", Tensor("0", (3, 2), (1, 3))), ("b", Tensor("1", (2,), (1,)))])},
                  {"0": [1, 2, 3, 4, 5, 6], "1": [0.5, -0.25]})
        out = run("c = w.load_checkpoint(sys.argv[1]); s = c['model_state_dict']\n"
                  "print(json.dumps(dict(dims=c['dims'], w=s['w'].tolist(), w_t=s['w_t'].tolist(), b=s['b'].tolist(),"
                  " dtype=str(s['w'].dtype))))", str(self.path))
        self.assertEqual(out["dims"], {"n_vocab": 51865})
        self.assertEqual(out["w"], [[1, 2, 3], [4, 5, 6]])
        self.assertEqual(out["w_t"], [[1, 4], [2, 5], [3, 6]])
        self.assertEqual((out["b"], out["dtype"]), ([0.5, -0.25], "float16"))

    def test_a_checkpoint_that_names_anything_but_tensors_is_refused(self):
        class Shell:
            def __reduce__(self):
                return os.system, ("echo pwned",)

        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("archive/data.pkl", pickle.dumps({"dims": Shell()}, protocol=2))
        with self.assertRaises(AssertionError) as refused:
            run("w.load_checkpoint(sys.argv[1])", str(self.path))
        self.assertIn("is not expected in a Whisper checkpoint", str(refused.exception))


@unittest.skipUnless(PYTHON, "the dictation engine's Python is not available")
class TokenizerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        ranks = [bytes([b]) for b in range(256)] + [b"ab", b"abc", b" a"]
        self.path = pathlib.Path(self.tmp.name) / "tiny.tiktoken"
        self.path.write_text("".join(f"{base64.b64encode(token).decode()} {rank}\n" for rank, token in enumerate(ranks)))

    def tokenizer(self, script):
        return run(f"t = w.build_tokenizer(sys.argv[1], num_languages=2)\n{script}", str(self.path))

    def test_text_is_split_by_the_ranks_in_openais_file(self):
        ids = self.tokenizer("print(json.dumps([t.encode(x, add_special_tokens=False).ids for x in "
                             "('abc', 'ab ab', 'a')]))")
        self.assertEqual(ids, [[257], [256, 32, 256], [97]], "the lowest-ranked merge wins: ab before \" a\"")

    def test_the_special_tokens_follow_the_vocabulary_in_openais_order(self):
        names = self.tokenizer("print(json.dumps([t.id_to_token(i) for i in range(259, 271)]))")
        self.assertEqual(names, ["<|endoftext|>", "<|startoftranscript|>", "<|en|>", "<|zh|>", "<|translate|>",
                                 "<|transcribe|>", "<|startoflm|>", "<|startofprev|>", "<|nospeech|>",
                                 "<|notimestamps|>", "<|0.00|>", "<|0.02|>"])

    def test_text_comes_back_as_it_went_in(self):
        text = self.tokenizer("print(json.dumps(t.decode(t.encode('ab abc', add_special_tokens=False).ids)))")
        self.assertEqual(text, "ab abc")


if __name__ == "__main__":
    unittest.main()
