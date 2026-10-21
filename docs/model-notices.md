# Model and runtime provenance

The experiment uses [google/flan-t5-small](https://huggingface.co/google/flan-t5-small),
revision `0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab`. The upstream model card declares
Apache-2.0 and describes a roughly 77 million parameter instruction-tuned model.
The model is selected for feasible CPU execution, not strong agent capabilities.
Weights are downloaded separately and not redistributed. Their seven file hashes
are committed in data/model-hashes.json and enforced before model loading.

The first local run reused an existing copy of those exact public model files by
copying them read-only from the sibling RAG project's cache to this repository's
own cache. No sibling file was modified. `download` fetches the same revision for
independent reproduction. Inference uses local files only and safetensors.

requirements-local.lock pins the measured Intel macOS Python 3.11.13 inference
stack, including torch 2.2.2 and transformers 4.46.3. This is a reference environment
lock, not a promise that native wheels exist for every platform. Portable evaluator
CI uses Python 3.11.9 on Linux, macOS and Windows without installing model libraries.
Those CI runs do not establish neural inference parity across operating systems.

No paid API or hosted model execution is used. Download traffic is not inference.
Library dependencies retain their respective upstream licenses. Original code,
fixtures, documents and result traces in this repository use MIT.
