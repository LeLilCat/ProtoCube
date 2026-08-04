# ProtoCube local-brain prototype

An interactive Windows desktop pet with event-driven physics and three modular,
fully local brain slots. It does not contact an online AI service during chat.

## Interactions

- Drag ProtoCube with the left mouse button and release it to throw.
- Click without dragging to play the boop sound and open the chat input.
- Drop a supported text/code file onto the square, then ask about it.
- Press **Enter** to submit a prompt.
- Right-click ProtoCube and choose **Chat history** to review previous messages.
- Choose **Brain mode** from the same menu to select Auto, Casual, Smart, or Deep.
- Toggle per-word **Talking sound** from the right-click menu without disabling mouth animation.
- Right-click for chat, memory, response cancellation, brain unloading, and quit options.
- ProtoCube can land on and follow the title bar of ordinary application windows.
- Physics stops updating after the square settles on the work-area floor.

Window sitting uses a cached surface map: windows are enumerated at 4 Hz only
while ProtoCube is moving. After landing, physics and enumeration stop; just the
landed-on window is tracked at 10 Hz, temporarily rising to about 30 Hz while it
moves. System-audio listening uses separate adaptive sampling described below.

## Workflow utilities

### Dynamic idle moods

`config.py` defines an event-driven `IDLE_PHASES` list. The defaults are Happy
from 0–2 minutes, Casual Chatter from 2–5 minutes, Lonely from 5–10 minutes, and
Crying after 10 minutes. Each phase can independently set:

- `inactivity_ms`: absolute phase start time after the last interaction.
- `chatter_interval_ms`: randomized `(minimum, maximum)` delay, or `None`.
- `lines`: local idle lines; these do not load or query an AI model.
- `image_dir` and `fallback_image_dir`: folder-discovered mood frames.
- `animate` and `frame_interval_ms`: optional sprite animation.
- `sound_dir`, `loop_sound`, `talk_sound`, and `bubble_duration_ms`: phase audio and bubble behavior.
- `system_audio_listening`: whether that mood may react to Windows output audio.

Set `ENABLE_IDLE_MOOD_PHASES = False` to restore strict pull-only behavior. Put
custom Lonely frames in `assets/image/lonely`, Crying frames in
`assets/image/crying`, and `.mp3`/`.wav` crying sounds in `assets/sfx/crying`.
Mouse interaction, file drops, prompts, hotkeys, and chat/history controls reset
the phase clock immediately. The implementation uses one phase timer and one
chatter timer rather than continuous polling.

`IDLE_MOOD_DISABLED_BRAIN_MODES` disables the system for selected brain keys.
Deep is included by default. Add a custom mode's registered key to this set to
disable idle moods there as well; returning to another mode restarts at Phase 0.

### Adaptive system-audio listening

When listening sprites exist, ProtoCube checks the Windows output peak at 4 Hz
while the system is quiet and temporarily switches to 20 Hz while audio is
active. After 800 ms of silence it returns to the slow interval. ProtoCube's own
speech, music, reactions, crying, eating, spawn sound, and model work suppress
listening so it does not react to itself.

Click sounds suppress listening for the selected clip's measured duration plus
`CLICK_SOUND_LISTENING_TAIL_MS`. If a clip reports no duration, ProtoCube uses
`CLICK_SOUND_LISTENING_FALLBACK_MS`; rapid clicks extend the suppression window.

Tune or disable this in `config.py` with `ENABLE_LISTENING_ANIMATION`,
`LISTENING_IDLE_POLL_INTERVAL_MS`, `LISTENING_ACTIVE_POLL_INTERVAL_MS`, the two
loudness thresholds, release delay, and animation-frame interval limits. The
Windows audio interfaces are explicitly released during shutdown.

### Drag-and-drop context

Drop up to three text/code files directly onto ProtoCube. Supported formats
include Python, JavaScript/TypeScript, C/C++, PowerShell, AutoHotkey, JSON,
Markdown, logs, configuration files, and other common text formats.

Attached text is capped at 4,800 characters; each mode's model context is set in
its own `brains/<mode>/brain.py` profile. The
attachment is marked as untrusted reference data, routed to Smart mode when Auto
is selected, and consumed after one successful answer.

### Clipboard diagnosis hotkey

Copy a code block or error message and press **Ctrl+Shift+Space**. ProtoCube sends
the current text clipboard to Smart mode and displays a concise diagnosis. It
reads the clipboard only when this hotkey is pressed.

The native Windows `RegisterHotKey` API is used; no low-level keyboard hook or
administrator permission is required. The right-click menu reports if another
application has already reserved the shortcut.

### Chat history

Choose **Chat history** from ProtoCube's right-click menu to open a scrollable
transcript. The display keeps up to 100 session messages within a
50,000-character memory cap. **Clear history** clears the visible transcript and
all three bounded model histories. Casual, Smart, and Deep histories are
isolated, so changing modes cannot leak one mode's persona or context into another.

### Confirmed system actions

ProtoCube loads named actions from `actions.json`. Use `/actions`, `/run name`,
or the right-click **System actions** menu. Every action requires confirmation.

Only two action types are supported:

- `open_folder` opens a path contained within the ProtoCube project.
- `run_script` launches a configured `.py`, `.bat`, `.ps1`, `.ahk`, or `.exe`
  contained within the `actions` folder.

Paths are resolved and checked before execution, arguments are static values from
the configuration, and commands run with `shell=False`. Natural-language model
output and `[CMD: ...]` strings are never executed. See `actions/README.md` for
configuration examples.

## Brain modes

| Mode | Model | Compute | Behavior |
| --- | --- | --- | --- |
| Auto | Chooses Casual or Smart | CPU or hybrid | Simple chat uses Casual; code and analysis use Smart; never selects Deep |
| Casual (CPU) | One GGUF from `models/casual` | CPU only | Short, playful conversation |
| Smart (Hybrid) | One GGUF from `models/smart` | Vulkan GPU + CPU/RAM overflow | Moderately complex work with a reasonable-size model |
| Deep (Experimental Hybrid) | One GGUF from `models/deep` | Vulkan GPU + CPU/RAM overflow | Explicit-only experiments with a large, slow model |

The default setup installs Qwen2.5 1.5B Q5_K_M in the Casual slot and Qwen2.5 3B
Q4_K_M in the Smart slot.

Smart and Deep use llama.cpp automatic fitting (`-ngl auto`) with a configurable
VRAM reserve. Layers that fit are offloaded to the RTX GPU; remaining layers stay
in system RAM and are computed by the CPU. This is deliberate partial offload,
not Windows shared-GPU-memory fallback.

No model loads until a prompt is submitted. Casual and Smart may remain loaded
together so Auto mode can switch without reloading on every prompt; their idle
timeouts are ten and five minutes. Deep is exclusive: its worker unloads both
other modes first, and switching away unloads Deep. Deep unloads after 90 seconds.

Prompt shortcuts override the selected mode:

- `/casual your question` forces the CPU brain (`/pet` remains an alias).
- `/smart your question` forces the Smart hybrid brain.
- `/deep your question` forces the experimental Deep hybrid brain.
- `/reset` clears the bounded in-memory conversation history.
- `/actions` lists configured system actions.
- `/run action_name` requests confirmation for an allowlisted action.

## First-time setup

The checked-in setup downloads only into this ProtoCube directory and verifies
every artifact by exact size and SHA-256.

1. Create the Python environment if it does not already exist:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Double-click `setup_brains.bat`, or run:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_brains.ps1
   ```

3. Double-click `run_prototype.bat`.

If double-clicking appears to do nothing, run `debug_prototype.bat`. It keeps a
console open for the error and writes the same traceback to
`protocube_startup.log` in this folder. Running setup again is not required for
ordinary launches.

The default setup downloads roughly 3.5 GB for Casual and Smart plus the CPU and
Vulkan runtimes. It creates the Deep slot but intentionally downloads no Deep
model. Custom model sizes are additional.

## Customization folders

ProtoCube discovers resources by folder rather than by a fixed filename:

- `assets/image/idle/`: first `.png`, `.jpg`, `.jpeg`, `.webp`, or `.bmp` file.
- `assets/sfx/click/`: all `.mp3` and `.wav` files, played in shuffled round-robin order with overlapping playback.
- `assets/sfx/hit_wall/`: one shuffled collision layer on every hard impact.
- `assets/sfx/hurt/`: a separate shuffled pain layer played simultaneously with the collision layer.
- `assets/sfx/talk/`: first `.mp3` or `.wav` file, replayed once per valid word in a reply.
- `assets/sfx/dead/`: one shuffled sound is opened only when ProtoCube closes; the window hides immediately and exits after playback.
- `models/casual/`: exactly one `.gguf` model, run on CPU.
- `models/smart/`: exactly one `.gguf` model, run with automatic hybrid offload.
- `models/deep/`: exactly one user-supplied `.gguf` model for experimental hybrid use.

The idle image and talking sound use the first supported file alphabetically.
`ENABLE_TALK_SOUND` in `config.py` controls the startup default; the right-click
toggle changes it for the current session.
Click sounds are shuffled, then each is played once before the next shuffle; the
same sound is not repeated across cycle boundaries. Each click sound can use up
to four playback voices so rapid clicks can overlap; extra voices are opened
lazily. Edit `CLICK_SOUND_VOICES` in `config.py` to change that limit. Model folders are stricter: ProtoCube
reports an error unless exactly one GGUF is present.

To swap a model, quit ProtoCube, replace the GGUF in the appropriate slot, and
start ProtoCube again. The replacement must be compatible with the bundled
llama.cpp version and should contain a usable chat template. Running
`setup_brains.bat` preserves a custom GGUF instead of replacing it with Qwen.

## Development run

```powershell
.\.venv\Scripts\python.exe main.py
```

Use `pythonw.exe` instead when you do not want a console window.

## Main files

- `main.py`: small application entry point.
- `pet_window.py`: pet interaction, drag/drop, animations, and feature coordination.
- `ui_components.py`: chat bubble, input, and history windows.
- `asset_manager.py`: folder discovery, pre-scaled images, word counting, and conservative food detection.
- `audio_manager.py`: owned MCI clips and lazy overlapping sound banks.
- `system_audio_listener.py`: adaptive WASAPI peak sampling and cleanup.
- `physics_engine.py`: screen-bound physics calculations.
- `idle_mood.py`: event-driven inactivity phase and chatter scheduling.
- `win32_integration.py`: global hotkeys and non-blocking media-key dispatch.
- `brain.py`: routing, local server lifecycle, bounded history, and generation.
- `brains/casual/brain.py`: Casual prompt and all Casual runtime parameters.
- `brains/smart/brain.py`: Smart prompt, hybrid fit, and generation parameters.
- `brains/deep/brain.py`: Deep prompt, hybrid fit, and generation parameters.
- `system_actions.py`: confined action validation and execution.
- `actions.json`: editable action allowlist.
- `actions/`: the only folder from which configured scripts can run.
- `setup_brains.ps1`: pinned and checksum-verified local runtime/model setup.
- `run_prototype.bat`: no-console prototype launcher.
- `debug_prototype.bat`: visible diagnostic launcher for startup failures.
- `launcher.py`: records otherwise-hidden `pythonw.exe` startup failures.

Physics parameters and customization folders are centralized in `config.py`.
Edit the corresponding `brains/<mode>/brain.py` to change its prompt, context,
GPU-layer policy, VRAM reserve, threads, batches, temperature, output limit, or
idle timeout without affecting the other modes.
