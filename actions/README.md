# ProtoCube actions

Only scripts placed in this folder can be launched by `run_script` actions.
Every action must be named in `../actions.json`, and ProtoCube asks for
confirmation before execution.

Supported local file types are `.py`, `.bat`, `.ps1`, `.ahk`, and `.exe`.
AutoHotkey scripts additionally require `AutoHotkey64.exe` at
`../runtime/autohotkey/AutoHotkey64.exe` so the action stays portable.

Example configuration:

```json
{
  "actions": {
    "my_macro": {
      "enabled": true,
      "type": "run_script",
      "path": "my_macro.ahk",
      "arguments": [],
      "description": "my local workspace macro"
    }
  }
}
```

Run it from chat with `/run my_macro`, or select it from the right-click menu.
