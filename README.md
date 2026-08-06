# ProtoCube

A lightweight Virtual pet assistant that's goofing around on your desktop!

### Features:
- Modular assets/model: All assets inside the "assets" folder can be replaced with your own. (png, wepb, animated gif, and go on!) And use your own .gguf files for your ProtoCube's brain.
- Commands: /sing {files name}, /casual {user's prompt}, /smart {user's prompt}, /deep {user's prompt}, /global stop; resume; prev; next, /<{N}; />{N} (jump the playhead inside ProtoCube /sing command), /stop; /resume; /prev; /next; /speedup {N}; /slowdown {N}; /speed {N} (commands for /sing)
- Physics system: ProtoCube can be thrown around the desktop with simple, lightweight Python math.


### First-time setup
1. Run "py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt" inside the folder of ProtoCube
2. Run setup_brains.bat
3. Run run_prototype.bat
