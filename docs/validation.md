# Validation record

## Hardware run

On 2026-10-03, build `dc0fdb9108332f34` completed 20 suites on a PS5 CFI-1215A, firmware `12.700.001`:

- **120 GPU dispatches; 10,920 exact output matches.**
- Zero output, input, or guard errors.
- Tracked tensor/shader buffers returned to **0 bytes**; peak **262,144 bytes**.
- Whole diagnostic task elapsed time: **26.562 seconds**, including repeated compilation, logging, validation, UI, submission, waits, and readback.
- Native 1920×1080 VideoOut setup and its first exact flip event succeeded.
- Browser-to-console task submission and completion succeeded.

[validation.json](evidence/validation.json) records the summary and digests. [gpu-readback-20-suites.txt.gz](evidence/gpu-readback-20-suites.txt.gz) retains all captured `ML_VALUE`, `ML_RESULT`, `ML_PASS`, and `PS5VK_QUEUE_COMPLETED` lines. `ML_BOOT` lines retain only the build identifier. Other runtime lines, process identifiers, network settings, and full logs are omitted. The gzip timestamp is fixed at zero.

```sh
python tools/verify_results.py docs/evidence/gpu-readback-20-suites.txt.gz
```

Expected: `verified: true`, `suites: 20`, `gpu_dispatches: 120`, `values: 10920`, `exact_rational_match: true`.

This trace lets readers check the numerical and capture-completeness claims. It is a recorded experiment, not independently attested proof of the hardware on which it ran.

## Workload

Three deterministic input sets each execute two FP32 kernels: `[7,16] × [16,13]` matrix multiplication and the same multiplication with bias plus ReLU. Each dispatch writes 91 outputs. Output regions are poisoned before dispatch; guard regions surround tensor data. The app waits for completion, invalidates mapped memory, then checks outputs against a separate CPU reference, inputs against their initial values, and untouched guards.

The host verifier uses exact rational arithmetic. Inputs are powers-of-two fractions, so this deliberately small workload can be compared exactly; that is not a numerical-accuracy guarantee for arbitrary models.

## What the numbers do not mean

- Dispatch time includes submission, waiting, and readback. It is not GPU-only timing, throughput, utilization, or a competitive benchmark.
- Allocation tracking covers the backend's tensor/shader buffers. It excludes command mappings, compiler/runtime memory, and the UI's separate 32 MiB framebuffer allocation. Zero tracked bytes does not prove every runtime allocation was reclaimed.
- Temperature calls were unavailable in this app context. GPU utilization is not exposed. Both remain unavailable in the dashboards.
- Controller initialization and handle creation succeeded, but the controller was reported disconnected; physical buttons have not been verified.
- A console display flip was confirmed. Visual inspection used a host-rendered preview, not a human-confirmed TV capture.
- These results do not test ExecuTorch, arbitrary model import, training, or LLM execution.

## Public-source changes

The recorded build predates public packaging. The public version adds configurable host settings, pinned dependency bootstrap, an OFL font and project icon, stricter host evidence checks, and file-only console logging instead of a fixed TCP logging address. Its compiled artifacts therefore have a different build identifier. The preserved result should not be represented as a fresh hardware run of the public commit.

The host tests reject missing/duplicate outputs, wrong values, unknown cases, guard errors, missing pass markers, duplicate completion tokens/results, and failure markers. A source build and host preview are separate checks from running a newly built artifact on a PS5.

Publication checks on 2026-10-03: PSBC was rebuilt with the checksum-pinned community SDK v0.43; the dashboard compiled and packaged successfully as build `185672a12e3c54b1`. All 15 host tests passed, including local HTTP request boundaries. Python and launcher syntax checks passed, and the Barlow-font preview was rendered and visually inspected. This rebuilt application was not deployed for a new hardware run.
