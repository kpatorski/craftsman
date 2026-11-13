#!/usr/bin/env python3
"""Turns OpenAI's own Whisper checkpoint into the model the dictation engine runs -- see REVIEW.md, "Dictation".

Usage (with the dictation engine's Python, which has numpy, ctranslate2 and tokenizers):
    whisper_convert.py <checkpoint.pt> <multilingual.tiktoken> <alignment heads> <output dir>

OpenAI publishes the weights as a PyTorch checkpoint and the tokenizer as a tiktoken file; faster-whisper reads a
CTranslate2 model and a `tokenizers` tokenizer. This writes both from OpenAI's files alone, without PyTorch: the
checkpoint is read as the zip of a pickle and raw arrays it is, the weights are laid into CTranslate2's Whisper
specification the way its own converter lays them, and the decoding settings -- the tokens never to produce, the
language tokens, the attention heads that time each word -- are worked out the way openai-whisper works them out.
The alignment heads are the base85 string openai-whisper keeps for each model (`whisper/__init__.py`).
"""
import base64
import collections
import gzip
import pickle
import sys
import zipfile

import numpy as np
from ctranslate2.converters import utils
from ctranslate2.converters.converter import Converter
from ctranslate2.specs import whisper_spec
from tokenizers import AddedToken, Tokenizer, decoders, models, pre_tokenizers

# openai-whisper's language codes, in the order of their tokens (whisper/tokenizer.py, LANGUAGES)
LANGUAGES = (
    "en zh de es ru ko fr ja pt tr pl ca nl ar sv it id hi fi vi he uk el ms cs ro da hu ta no th ur hr bg lt la mi ml "
    "cy sk te fa lv bn sr az sl kn et mk br eu is hy ne mn bs kk sq sw gl mr pa si km sn yo so af oc ka be tg sd gu am "
    "yi lo uz fo ht ps tk nn mt sa lb my bo tl mg as tt haw ln ha ba jw su yue").split()
CONTROL = ["<|translate|>", "<|transcribe|>", "<|startoflm|>", "<|startofprev|>", "<|nospeech|>", "<|notimestamps|>"]
TIMESTAMPS = 1501  # <|0.00|> to <|30.00|>, every 0.02 s
STORAGES = {"HalfStorage": np.float16, "FloatStorage": np.float32}


def load_checkpoint(path):
    """`torch.save`'s zip format read without torch: a pickle whose tensors point at raw arrays in the archive.
    Anything in the pickle other than tensors, dicts and numbers is refused."""
    archive = zipfile.ZipFile(path)
    root = archive.namelist()[0].split("/")[0]

    def rebuild_tensor(storage, offset, size, stride, *_):
        if not size:
            return storage[offset:offset + 1].reshape(())
        return np.lib.stride_tricks.as_strided(storage[offset:], shape=size,
                                               strides=[step * storage.itemsize for step in stride]).copy()

    class Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            if (module, name) == ("torch._utils", "_rebuild_tensor_v2"):
                return rebuild_tensor
            if module == "torch" and name in STORAGES:
                return name
            if (module, name) == ("collections", "OrderedDict"):
                return collections.OrderedDict
            raise pickle.UnpicklingError(f"{module}.{name} is not expected in a Whisper checkpoint")

        def persistent_load(self, pid):
            _, kind, key, _, _ = pid
            return np.frombuffer(archive.read(f"{root}/data/{key}"), dtype=STORAGES[kind])

    with archive.open(f"{root}/data.pkl") as raw:
        return Unpickler(raw).load()


def _bytes_to_unicode():
    """GPT-2's byte -> printable character table, which byte-level BPE vocabularies are written in."""
    printable = [*range(ord("!"), ord("~") + 1), *range(ord("¡"), ord("¬") + 1), *range(ord("®"), ord("ÿ") + 1)]
    table, extra = {b: chr(b) for b in printable}, 0
    for b in range(256):
        if b not in table:
            table[b] = chr(256 + extra)
            extra += 1
    return table


def _merge_parts(ranks, token, rank):
    """The two parts BPE joins to make `token`: merge its bytes by rank, using only merges ranked before it."""
    parts = [bytes([b]) for b in token]
    while True:
        best = None
        for i in range(len(parts) - 1):
            found = ranks.get(parts[i] + parts[i + 1])
            if found is not None and found < rank and (best is None or found < best[1]):
                best = (i, found)
        if best is None:
            return parts
        i = best[0]
        parts[i:i + 2] = [parts[i] + parts[i + 1]]


def build_tokenizer(tiktoken_path, num_languages):
    """The tokenizer faster-whisper reads, from OpenAI's tiktoken file: the same BPE, the same token ids."""
    with open(tiktoken_path, "rb") as raw:
        ranks = {base64.b64decode(token): int(rank) for token, rank in (line.split() for line in raw if line.strip())}
    table = _bytes_to_unicode()
    text = lambda token: "".join(table[b] for b in token)  # noqa: E731
    vocab, merges = {}, []
    for token, rank in ranks.items():
        vocab[text(token)] = rank
        if len(token) > 1:
            parts = _merge_parts(ranks, token, rank)
            if len(parts) == 2:
                merges.append((text(parts[0]), text(parts[1])))
    tokenizer = Tokenizer(models.BPE(vocab=vocab, merges=merges))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    special = ["<|endoftext|>", "<|startoftranscript|>"] + [f"<|{code}|>" for code in LANGUAGES[:num_languages]]
    tokenizer.add_special_tokens([AddedToken(token, special=True, normalized=False) for token in special + CONTROL])
    tokenizer.add_tokens([AddedToken("<|%.2f|>" % (i * 0.02), normalized=True) for i in range(TIMESTAMPS)])
    return tokenizer


def non_speech_tokens(tokenizer):
    """openai-whisper's Tokenizer.non_speech_tokens: tokens for speaker tags and sound notes, never spoken."""
    encode = lambda text: tokenizer.encode(text, add_special_tokens=False).ids  # noqa: E731
    symbols = list('"#()*+/:;<=>@[\\]^_`{|}~「」『』')
    symbols += "<< >> <<< >>> -- --- -( -[ (' (\" (( )) ((( ))) [[ ]] {{ }} ♪♪ ♪♪♪".split()
    miscellaneous = set("♩♪♫♬♭♮♯")
    result = {encode(" -")[0], encode(" '")[0]}
    for symbol in symbols + sorted(miscellaneous):
        for tokens in (encode(symbol), encode(" " + symbol)):
            if len(tokens) == 1 or symbol in miscellaneous:
                result.add(tokens[0])
    return sorted(result)


class _Linear:
    def __init__(self, weight, bias=None):
        self.weight, self.bias = weight, bias

    def has_bias(self):
        return self.bias is not None


class WhisperCheckpoint(Converter):
    def __init__(self, checkpoint, tokenizer, alignment_heads):
        self.dims, self.weights = checkpoint["dims"], checkpoint["model_state_dict"]
        self.tokenizer, self.alignment_heads = tokenizer, alignment_heads

    def _load(self):
        dims, w = self.dims, self.weights
        spec = whisper_spec.WhisperSpec(dims["n_audio_layer"], dims["n_audio_head"], dims["n_text_layer"],
                                        dims["n_text_head"])

        def linear(target, name):
            target.weight = w[f"{name}.weight"]
            if f"{name}.bias" in w:
                target.bias = w[f"{name}.bias"]

        def norm(target, name):
            target.gamma, target.beta = w[f"{name}.weight"], w[f"{name}.bias"]

        def attention(target, name, self_attention):
            query = _Linear(w[f"{name}.query.weight"], w[f"{name}.query.bias"])
            key = _Linear(w[f"{name}.key.weight"])  # Whisper's key projection has no bias
            value = _Linear(w[f"{name}.value.weight"], w[f"{name}.value.bias"])
            if self_attention:
                utils.fuse_linear(target.linear[0], [query, key, value])
            else:
                utils.fuse_linear(target.linear[0], [query])
                utils.fuse_linear(target.linear[1], [key, value])
            linear(target.linear[-1], f"{name}.out")

        def block(target, name, cross):
            attention(target.self_attention, f"{name}.attn", True)
            norm(target.self_attention.layer_norm, f"{name}.attn_ln")
            if cross:
                attention(target.attention, f"{name}.cross_attn", False)
                norm(target.attention.layer_norm, f"{name}.cross_attn_ln")
            linear(target.ffn.linear_0, f"{name}.mlp.0")
            linear(target.ffn.linear_1, f"{name}.mlp.2")
            norm(target.ffn.layer_norm, f"{name}.mlp_ln")

        encoder, decoder = spec.encoder, spec.decoder
        linear(encoder.conv1, "encoder.conv1")
        linear(encoder.conv2, "encoder.conv2")
        encoder.position_encodings.encodings = w["encoder.positional_embedding"]
        norm(encoder.layer_norm, "encoder.ln_post")
        for i, layer in enumerate(encoder.layer):
            block(layer, f"encoder.blocks.{i}", cross=False)
        decoder.embeddings.weight = w["decoder.token_embedding.weight"]
        decoder.position_encodings.encodings = w["decoder.positional_embedding"]
        norm(decoder.layer_norm, "decoder.ln")
        for i, layer in enumerate(decoder.layer):
            block(layer, f"decoder.blocks.{i}", cross=True)
        decoder.projection.weight = w["decoder.token_embedding.weight"]  # Whisper ties the output to the embedding

        tokenizer, token = self.tokenizer, self.tokenizer.token_to_id
        spec.register_vocabulary([tokenizer.id_to_token(i) for i in range(dims["n_vocab"])])
        config = spec.config
        config.suppress_ids = sorted(set(non_speech_tokens(tokenizer)) | {token(name) for name in (
            "<|transcribe|>", "<|translate|>", "<|startoftranscript|>", "<|startofprev|>", "<|startoflm|>",
            "<|nospeech|>")})
        config.suppress_ids_begin = tokenizer.encode(" ", add_special_tokens=False).ids + [token("<|endoftext|>")]
        config.lang_ids = list(range(token("<|startoftranscript|>") + 1, token("<|translate|>")))
        heads = np.frombuffer(gzip.decompress(base64.b85decode(self.alignment_heads)), dtype=bool)
        config.alignment_heads = [[int(layer), int(head)] for layer, head in
                                  np.argwhere(heads.reshape(dims["n_text_layer"], dims["n_text_head"]))]
        return spec


def convert(checkpoint_path, tiktoken_path, alignment_heads, output_dir):
    checkpoint = load_checkpoint(checkpoint_path)
    n_vocab = checkpoint["dims"]["n_vocab"]
    if n_vocab < 51865:
        raise SystemExit("only the multilingual Whisper models are supported")
    tokenizer = build_tokenizer(tiktoken_path, num_languages=n_vocab - 51765 - 1)
    WhisperCheckpoint(checkpoint, tokenizer, alignment_heads).convert(output_dir, quantization="float16", force=True)
    tokenizer.save(f"{output_dir}/tokenizer.json")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__.split("\n\n")[1])
    convert(*sys.argv[1:])
