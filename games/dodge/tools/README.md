# PORTTEST — CIA1 joystick port probe

A tiny diagnostic PRG for TheC64 port-routing questions (built during the
Last Galaxy classic-mode investigation — see `spec/behaviors.yaml`
System 3 for the finding it confirmed).

Shows both CIA1 joystick ports live on screen, active-high (bit set =
line grounded / direction or fire held):

```
CIA1 JOYSTICK PORT PROBE
P2 DC00 = XX      ← red   — Control Port 2 (bits 0-4: U D L R F)
P1 DC01 = XX      ← yellow — Control Port 1 (bits 0-4: U D L R F)
```

P1 bits 5–7 are keyboard row lines; they only move if a real key
grounds them (a port-1 joystick cannot touch them).  IRQs are off so
the KERNAL keyboard scan cannot flip DDRA while reading.

## Use case

TheC64 classic mode assigns the joystick port by the launch device
(keyboard launch → Port 1, joystick FIRE launch → Port 2).  Launch
this PRG both ways and watch which row responds — 10 seconds, no
guesswork.  Also handy for testing CJM `J:` overrides and ☰+A/B
port swaps mid-session.

## Build

```sh
acme -f cbm -o portprobe.prg portprobe.a
c1541 -format "PORTTEST,01" d64 portprobe.d64 -write portprobe.prg PORTTEST
```

Copy `portprobe.d64` (or the `.prg`) to TheC64 USB stick and load it
like any game.  Verified in VICE (idle reads `00`/`00` with no stick).
