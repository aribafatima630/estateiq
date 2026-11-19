from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


try:
    from scipy.special import erf as _erf
except Exception:  # pragma: no cover - tanh approximation still ranks related text
    _erf = None


def _gelu(value: np.ndarray) -> np.ndarray:
    if _erf is None:
        inner = np.sqrt(2.0 / np.pi) * (value + 0.044715 * np.power(value, 3))
        return 0.5 * value * (1.0 + np.tanh(inner))
    return 0.5 * value * (1.0 + _erf(value / np.sqrt(2.0)))


def _layer_norm(value: np.ndarray, weight: np.ndarray, bias: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    mean = value.mean(axis=-1, keepdims=True)
    variance = value.var(axis=-1, keepdims=True)
    normalized = (value - mean) / np.sqrt(variance + eps)
    return normalized * weight + bias


def _linear(value: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    return value @ weight.T + bias


class MiniLMNumpy:
    """Mean-pooled all-MiniLM-L6-v2 forward pass.

    This uses the published Sentence Transformers weights. It exists for machines
    where the PyTorch DLL cannot load, and it produces the same embedding space.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from huggingface_hub import hf_hub_download
        from safetensors.numpy import load_file
        from tokenizers import Tokenizer

        if "all-MiniLM-L6-v2" not in model_name:
            raise RuntimeError("The NumPy embedder only supports all-MiniLM-L6-v2.")
        logger.info("Loading MiniLM weights for %s", model_name)
        weights = load_file(hf_hub_download(model_name, "model.safetensors"))
        self.weights = {key: value.astype(np.float32) for key, value in self._normalise_keys(weights).items()}
        self.tokenizer = Tokenizer.from_file(hf_hub_download(model_name, "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self.layers = 6
        self.heads = 12
        self.head_dim = 32
        hidden = self.weights["embeddings.word_embeddings.weight"].shape[1]
        if hidden != self.heads * self.head_dim:
            raise RuntimeError("Unexpected MiniLM hidden size.")

    @staticmethod
    def _normalise_keys(weights: dict) -> dict:
        marker = "embeddings.word_embeddings.weight"
        sample = next(key for key in weights if key.endswith(marker))
        prefix = sample[: -len(marker)]
        return {key[len(prefix) :] if key.startswith(prefix) else key: value for key, value in weights.items()}

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype="float32")
        vectors = []
        batch_size = 8
        total = len(texts)
        for start in range(0, total, batch_size):
            if start == 0 or start % 80 == 0:
                logger.info("Embedding batch %s/%s", start // batch_size + 1, (total + batch_size - 1) // batch_size)
            vectors.append(self._embed_batch(texts[start : start + batch_size]))
        return np.vstack(vectors)

    def _embed_batch(self, texts: list[str]) -> np.ndarray:
        encoded = self.tokenizer.encode_batch(texts)
        input_ids = np.asarray([item.ids for item in encoded], dtype=np.int64)
        mask = np.asarray([item.attention_mask for item in encoded], dtype=np.float32)
        batch, length = input_ids.shape
        word = self.weights["embeddings.word_embeddings.weight"][input_ids]
        position_ids = np.arange(length)
        position = self.weights["embeddings.position_embeddings.weight"][position_ids]
        token_type = self.weights["embeddings.token_type_embeddings.weight"][0]
        hidden = word + position + token_type
        hidden = _layer_norm(
            hidden,
            self.weights["embeddings.LayerNorm.weight"],
            self.weights["embeddings.LayerNorm.bias"],
        )
        for layer in range(self.layers):
            hidden = self._layer(hidden, mask, layer)
        pooled = (hidden * mask[:, :, None]).sum(axis=1) / np.maximum(mask.sum(axis=1, keepdims=True), 1.0)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (pooled / norms).astype(np.float32)

    def _layer(self, hidden: np.ndarray, mask: np.ndarray, layer: int) -> np.ndarray:
        prefix = f"encoder.layer.{layer}."
        query = _linear(hidden, self.weights[prefix + "attention.self.query.weight"], self.weights[prefix + "attention.self.query.bias"])
        key = _linear(hidden, self.weights[prefix + "attention.self.key.weight"], self.weights[prefix + "attention.self.key.bias"])
        value = _linear(hidden, self.weights[prefix + "attention.self.value.weight"], self.weights[prefix + "attention.self.value.bias"])
        batch, length, _ = query.shape
        query = query.reshape(batch, length, self.heads, self.head_dim).transpose(0, 2, 1, 3)
        key = key.reshape(batch, length, self.heads, self.head_dim).transpose(0, 2, 1, 3)
        value = value.reshape(batch, length, self.heads, self.head_dim).transpose(0, 2, 1, 3)
        scores = query @ key.transpose(0, 1, 3, 2) / np.sqrt(self.head_dim)
        scores = scores + (1.0 - mask[:, None, None, :]) * -1e4
        scores = scores - scores.max(axis=-1, keepdims=True)
        weights = np.exp(scores)
        weights = weights / weights.sum(axis=-1, keepdims=True)
        context = weights @ value
        context = context.transpose(0, 2, 1, 3).reshape(batch, length, self.heads * self.head_dim)
        attention = _linear(
            context,
            self.weights[prefix + "attention.output.dense.weight"],
            self.weights[prefix + "attention.output.dense.bias"],
        )
        hidden = _layer_norm(
            hidden + attention,
            self.weights[prefix + "attention.output.LayerNorm.weight"],
            self.weights[prefix + "attention.output.LayerNorm.bias"],
        )
        intermediate = _gelu(
            _linear(
                hidden,
                self.weights[prefix + "intermediate.dense.weight"],
                self.weights[prefix + "intermediate.dense.bias"],
            )
        )
        output = _linear(
            intermediate,
            self.weights[prefix + "output.dense.weight"],
            self.weights[prefix + "output.dense.bias"],
        )
        return _layer_norm(
            hidden + output,
            self.weights[prefix + "output.LayerNorm.weight"],
            self.weights[prefix + "output.LayerNorm.bias"],
        )
