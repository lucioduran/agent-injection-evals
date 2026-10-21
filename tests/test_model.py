import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from injection_evals.model import CONFIG, FILES, MODEL_ID, REVISION, LocalModel, download, hashes


class ModelTests(unittest.TestCase):
    def test_download_pinned_files(self):
        hub = MagicMock()
        with patch.dict("sys.modules", {"huggingface_hub": hub}):
            download(Path("cache"))
        hub.snapshot_download.assert_called_once_with(
            MODEL_ID, revision=REVISION, local_dir=Path("cache"), allow_patterns=list(FILES)
        )

    def test_hashes_missing_or_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with self.assertRaises(FileNotFoundError):
                hashes(cache)
            for name in FILES:
                (cache / name).write_bytes(b"fixture")
            first = hashes(cache)
            (cache / FILES[0]).write_bytes(b"different")
            self.assertNotEqual(first, hashes(cache))
            with self.assertRaisesRegex(ValueError, "pinned artifact"):
                LocalModel(cache)

    def test_cpu_offline_greedy_and_budget(self):
        torch = MagicMock()
        transformers = MagicMock()
        expected = json.loads(Path("data/model-hashes.json").read_text())
        tokenizer = transformers.AutoTokenizer.from_pretrained.return_value
        tokenizer.return_value = {"input_ids": SimpleNamespace(shape=(1, 100))}
        tokenizer.decode.return_value = "ANSWER blue"
        model = transformers.AutoModelForSeq2SeqLM.from_pretrained.return_value.to.return_value.eval.return_value
        model.generate.return_value = [[0, 1, 2]]
        with (
            patch.dict("sys.modules", {"torch": torch, "transformers": transformers}),
            patch("injection_evals.model.hashes", return_value=expected),
        ):
            adapter = LocalModel(Path("cache"))
            result = adapter.generate("input")
            self.assertEqual(result["output_tokens"], 2)
            self.assertEqual(result["input_tokens"], 100)
            self.assertEqual(result["output"], "ANSWER blue")
            self.assertGreaterEqual(result["wall_seconds"], 0)
            torch.set_num_threads.assert_called_once_with(2)
            transformers.AutoModelForSeq2SeqLM.from_pretrained.assert_called_once_with(
                Path("cache"), local_files_only=True, use_safetensors=True
            )
            self.assertFalse(model.generate.call_args.kwargs["do_sample"])
            self.assertEqual(model.generate.call_args.kwargs["max_new_tokens"], 48)
            tokenizer.return_value = {
                "input_ids": SimpleNamespace(shape=(1, CONFIG["max_input_tokens"] + 1))
            }
            with self.assertRaisesRegex(ValueError, "truncation"):
                adapter.generate("too long")
