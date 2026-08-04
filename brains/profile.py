from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrainProfile:
    """All model, runtime, generation, and persona settings for one mode."""

    key: str
    display_name: str
    model_folder: str
    runtime_folder: str
    system_prompt: str
    context_tokens: int
    gpu_layers: int | str
    fit_vram: bool
    fit_target_mib: int
    threads: int
    threads_batch: int
    batch_size: int
    ubatch_size: int
    temperature: float
    top_p: float
    max_tokens: int
    startup_timeout_seconds: float
    request_timeout_seconds: float
    idle_seconds: float

    @property
    def uses_gpu(self) -> bool:
        return str(self.gpu_layers).casefold() not in {"0", "none"}

