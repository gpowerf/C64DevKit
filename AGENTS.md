# AGENTS.md — C64DevKit Development Guide

## Spec-Driven Development

**The spec is the single source of truth.** Every change begins with a spec update, never with assembly code. The workflow is:

```
spec change  →  build  →  test  →  commit
```

Reverse this and you're vibe coding. Don't.

### The Loop

1. **Change the spec** (`spec/*.yaml`) to describe what the program should do
2. **`c64devk build`** — regenerates assembly, assembles .prg
3. **`c64devk run`** — launch in VICE, verify behaviour
4. **`c64devk test`** — run assertions (requires VICE headless)
5. **`c64devk check`** — validate spec consistency before committing
6. **Commit** the spec changes (and any routine changes they required)

### What Goes Where

| File | Purpose | When to edit |
|------|---------|-------------|
| `spec/game.yaml` | Screen mode, colours, zones | Change visuals |
| `spec/sprites.yaml` | Sprite definitions (pos, colour, data) | Add/change sprites |
| `spec/behaviors.yaml` | DSL actions + complete game design doc | Any behaviour change |
| `spec/tests.yaml` | Test assertions via VICE monitor | Add tests for behaviour |
| `routines/game_logic.acme` | Custom 6502 assembly | When DSL can't express it |
| `c64devk.yaml` | Memory layout, project config | Memory planning |
| `assets/` | Binary data (sprites, charset) | Add sprite/art assets |

**If you edit `routines/`, you MUST also update `spec/behaviors.yaml`** to document the change. The spec is the documentation — even if the DSL can't generate the code yet, the spec describes what the code does.

### The Decision: DSL or Assembly?

Use the **behaviour DSL** when the action is:
- Joystick/keyboard → sprite movement (`update_sprite`)
- Collision → score/sound/reset (`on_collision` + `inc_score`, `play_sound`, `set_sprite_pos`)
- Periodic actions (`on_timer` + `every: N`)
- HUD text/numbers (`display_text`, `display_number`)
- Sprite visibility toggles (`enable_sprite`, `disable_sprite`)

Use **assembly routines** when you need:
- Custom AI (chase, patrol, state machines)
- Complex math (distance calculations, fractional speed)
- Direct hardware access (colour RAM, $D010 MSB)
- Visual effects (DMZ noise, raster bars)
- Keyboard input (beyond the DSL's joystick read)
- Anything with conditional logic the DSL can't express

**Aim for 50/50.** If your `game_logic.acme` is over 500 lines, consider whether some logic could move to the DSL. If your `behaviors.yaml` is mostly comments with no actions, consider whether more behaviour belongs in the DSL.

### The Contract

`spec/behaviors.yaml` serves double duty:
1. **DSL input** — actions generate assembly code
2. **Design document** — comments describe all systems, even those in routines

When you add a system in assembly, add a section in `behaviors.yaml` documenting:
- Variables declared and their purpose
- Algorithm and edge cases
- Constants and tables
- State transitions (if applicable)

The spec should be detailed enough to recreate the game from scratch.

### Build Commands

```bash
c64devk build              # Build current directory
c64devk build -p games/dodge  # Build specific project
c64devk run                 # Build and launch in VICE
c64devk run --headless      # Run without GUI (for test env)
c64devk test                # Run spec/tests.yaml assertions
c64devk test --static       # Static checks only, no VICE
c64devk check               # Validate specs (no build)
c64devk clean               # Remove output/
c64devk doctor              # Check toolchain
c64devk new <name>          # Scaffold new project
```

### When Extending the Framework

If the DSL can't express what you need, you have **two options**:

**Option A: Write it in routines** (immediate, documented in spec)
```yaml
# behaviors.yaml — documented but not codegen'd
# ──────────────────────────────────────────────────
# System: Enemy AI — chases player at fractional speed
# Variables: enemy_x, enemy_y, speed_ctr, speed_frac
# See: routines/game_logic.acme:enemy_do
```

**Option B: Extend the DSL** (investment, reusable)
1. Add a new action type in `codegen.py` (`_emit_action_*`)
2. Register it in the `action_emitters` dict
3. Add parsing support in `spec_parser.py` `Action._params_for_type()`
4. Document in `skills/SKILL.md`
5. Update templates if the action is commonly useful

Prefer Option A for game-specific logic. Prefer Option B for patterns you use across multiple projects.

### Code Conventions

- **6502 assembly in routines:**
  - Jump past variable data at file top (`jmp gstart` then `!byte` vars)
  - Labels use descriptive names (`enemy_do`, `collision_check`)
  - Use the framework's `random` variable for RNG (don't roll your own)
  - Address sprites by VIC-II register when speed matters, by variable when logic matters
  - Branch distance: if a branch target exceeds ±127 bytes, use the trampoline pattern:
    ```asm
    beq .skip           ; invert condition
    jmp .far_label
    .skip:
    ```
- **YAML comments use full sentences with proper punctuation.**
- **Variable names in spec comments must match assembly labels exactly.**
- **Memory layout changes go in `c64devk.yaml`**, not in routines (use `* =` sparingly).
- **Never edit `output/`.** It is regenerated on every build.

### Validation Rules

`c64devk build` and `c64devk check` enforce:
- `name` is non-empty
- `code_start` < `code_end` < `$D000`
- `sprite_data` is 64-byte aligned
- Sprite indices 0–7, no duplicates
- Sprite X: 0–511, Y: 0–255
- Behaviour action sprite references exist in `sprites.yaml`
- Collision sprite references exist in `sprites.yaml`

Additional checks from `c64devk check`:
- All spec files parse without error
- Data files referenced by sprites exist on disk
- Score/lives/level variables used in display are declared
- No orphaned labels (referenced but undefined)
- Routine file exists if `routines:` lists it in `c64devk.yaml`

### Project Layout Reference

```
mygame/
├── c64devk.yaml         # Memory layout, project config
├── spec/
│   ├── game.yaml        # Screen setup
│   ├── sprites.yaml     # Sprite definitions
│   ├── behaviors.yaml   # DSL actions + game design doc
│   └── tests.yaml       # Test assertions
├── routines/
│   └── game_logic.acme  # Custom 6502 (called each frame)
├── assets/
│   └── sprites/         # .spr files (64-byte raw data)
└── output/              # Generated (gitignore)
    ├── src/main.acme    # Generated assembly
    └── build/<name>.prg # Ready-to-run C64 program
```
