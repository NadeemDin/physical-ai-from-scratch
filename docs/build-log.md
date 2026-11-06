# Phase 0: Build log

Problems hit while building the rig: what happened, why and how it was fixed. If something in the [build guide](build.md) doesnt behave as described, look for the symptom here first.

## Quick index

| # | Symptom | Step | Status |
| --- | --- |---|----|
| 1| Arduino error: "redefinition of `void setup()`" | 1| Fixed |
| 2 | Upload fails: "Unable to verify flash chip connection" |1 | Fixed |
| 3 | The official USB driver won't install | 1 | Not needed |
| 4 | Arduino Serial Monitor shows a few good lines, then garbage | 1 | Workaround |
| 5 | Output in Terminal forms a diagonal "staircase" | 1 | Fixed |
| 6 | Upload fails: "port is busy" | 1 | Routine |
| 7 | Upload fails: "No such file or directory" for the port | 1 | Fixed |
| 8 | "AHT20 not found", then nothing more | 2 | Fixed |
| 9 | Typing a speed sets the fan to 0% | 6 | Fixed |
| 10 | RPM counted with no 12V connected | 6 | Expected |
| 11 | RPM reads ~751,000 (correct only at 100%) | 6 | Fixed |
| 12 | RPM about 10% too high in `all_sensors` | 7 | Fixed |
| 13 | TMP117 won't sit flat on the hub | 8 | Fixed |
| 14 | ADXL345 shifts on its tape | 8 | Fixed |
| 15 | Fan rocks front to back in its brackets | 8 | Accepted |

---
## 1. "redefinition of `void setup()`"
 
**When:** 31 Oct 2026, step 1
 
**What happened:** the Arduino IDE refused to compile, complaining that `setup()` was defined twice.
 
**Why:** two sketches were open as tabs in the same sketch window. Arduino joins all tabs in a window into one program, so it saw two `setup()` and two `loop()` functions.
 
**Fix:** one program per sketch. Use **File → New Sketch** for each step, and keep each sketch in its own folder (as in [`firmware/`](../firmware)).
 
---

## 2. "Unable to verify flash chip connection"
 
**When:** 31 Oct 2026, step 1
 
**What happened:** the upload started, then failed.
 
**Why:** the board talks to the Mac through a USB chip (a CH9102). macOS's built-in driver for it is unreliable at the Arduino IDE's default upload speed (921,600 baud, i.e. bits per second).
 
**Fix:** **Tools → Upload Speed → 115200.** Uploads take a little longer but work every time.
 
---

## 3. The official USB driver won't install
 
**When:** 31 Oct 2026, step 1
 
**What happened:** while chasing problem 4, I tried installing the USB chip maker's (WCH) own driver. The Install button did nothing, and macOS said an extension "needs to be updated by the developer".
 
**Why:** the package contains an old-style system extension that current macOS blocks.
 
**Fix:** not installed, and not needed. Everything works on macOS's built-in driver at Upload Speed 115200 (problem 2). Don't lower your Mac's security settings to force it in - its not worth it.
 
---

## 4. Serial Monitor shows a few good lines, then garbage
 
**When:** 31 Oct 2026, step 1
 
**What happened:** the Arduino IDE's Serial Monitor showed about three correct lines, then garbled characters, over and over.
 
**Why:** the Serial Monitor and macOS's built-in driver for this board's USB chip don't get on. The board itself was fine: the RGB status light showed it never restarted.
 
**Fix:** read the output in **Terminal** instead:
```
screen /dev/cu.usbserial-XXXX 115200
```
Exit with **Ctrl+A, then K, then Y**. This only matters while building; the finished rig sends its data over Wi-Fi.

---
 
## 5. Output forms a diagonal "staircase"
 
**When:** 31 Oct 2026, step 1
 
**What happened:** in `screen`, each new line started where the previous one ended, so the text marched diagonally across the window.
 
**Why:** a line ending is really two instructions: "go back to the start of the line" (carriage return, `\r`) and "go down a line" (newline, `\n`). The sketches only sent `\n`, and `screen` takes both literally.
 
**Fix:** every sketch now ends lines with `\r\n`.
 
---

## 6. Upload fails: "port is busy"
 
**When:** 31 Oct 2026, step 1, and any time after
 
**What happened:** the upload failed straight away.
 
**Why:** `screen` was still open and holding the USB connection. Only one program can use it at a time.
 
**Fix:** exit `screen` (**Ctrl+A, K, Y**) before every upload. Unplugging and replugging USB also frees it.
 
---

## 7. "No such file or directory" for the port
 
**When:** 31 Oct 2026, step 1
 
**What happened:** the `/dev/cu.usbserial-…` port disappeared, and uploads failed.
 
**Why:** the ESP32 was still pushed into the black anti-static foam it was shipped in. The foam conducts electricity slightly, so it partly short-circuited the pins while powered.
 
**Fix:** take the board out of the foam before plugging it in. Only store it in foam when it's unplugged.
 
---

## 8. "AHT20 not found", then nothing more
 
**When:** 31 Oct 2026, step 2
 
**What happened:** the sketch printed `AHT20 not found` once and then went silent.
 
**Why:** the sensor wasn't connected when the sketch started, and the original code gave up permanently.
 
**Fix:**
- Connect sensors with **USB unplugged**, then plug in.
- Sketches now **retry** instead of giving up, so they recover once the sensor is connected.
- Added the **RGB status light**, so the board's state is visible without a screen: red = just started, green/blue = all OK, amber/blue = something missing.
---
 
## 9. Typing a speed sets the fan to 0%
 
**When:** 2 Nov 2026, step 6
 
**What happened:** typing e.g. `60` and Enter in `screen` set the speed to 60%, then immediately to 0%, and the fan wound down.
 
**Why:** the original code used `Serial.parseInt()`, which reads a number from what you type. Pressing Enter sends an extra invisible character, which `parseInt()` read as a second, empty number: 0.
 
**Fix:** replaced it with a simple line reader. It collects digits as you type, applies the value only when you press Enter, ignores empty input, shows what you're typing, and confirms with `>> duty set to 60%`.
 
---

## 10. RPM counted with no 12V connected
 
**When:** 2 Nov 2026, step 6, while investigating problem 11
 
**What happened:** with the 12V adapter unplugged, the ESP32 still counted pulses on the tach wire. They stopped if either the PWM or tach wire was pulled out.
 
**Why:** with the fan unpowered, the 3.3V speed-control signal leaks through the fan's electronics and comes out on its tach wire.
 
**Fix:** none needed. It's expected, and RPM readings only mean something when the fan has 12V.
 
---

## 11. RPM reads ~751,000
 
**When:** 2 Nov 2026, step 6
 
**What happened:** at 40% the RPM read about **751,000**. A software filter brought it down to 12,000–14,700, which was still wrong. Only at 100% was it correct (3,150 RPM). The wiring was checked and was correct.
 
**Why:** the PWM wire switches on and off 25,000 times a second, and it runs right next to the tach wire. Every switch induced a tiny spike on the tach wire, and the ESP32 counted each spike as a fan pulse. The numbers fit: 25,000 spikes a second works out to about 751,000 RPM. At 100% the PWM signal barely switches, so there were no spikes and the reading was clean.
 
**Fix:** the ESP32 has a built-in **hardware pulse counter** (called PCNT) with a **glitch filter**. Set to 10 microseconds, the filter ignores anything shorter than that. The spikes last well under 1 microsecond, so they're discarded; real fan pulses last milliseconds, so they're still counted. No extra parts needed.
 
**If it ever comes back:** a small capacitor between the tach row and ground would smooth the spikes out in hardware.
 
**Result after the fix:** 50% → 1,680 RPM · 60% → 2,010 · 100% → 3,180.
 
---

## 12. RPM about 10% too high in `all_sensors`
 
**When:** 2 Nov 2026, step 7
 
**What happened:** `all_sensors` showed RPM about 10% higher than `fan_test` at the same speed setting.
 
**Why:** RPM is worked out from "pulses counted in one second". Reading all the other sensors made each loop take a bit **longer** than one second, so more pulses were counted per "second" than really happened in one.
 
**Fix:** the sketch now measures how long actually passed since the last reading (in milliseconds) and scales the count to match.
 
---

## 13. TMP117 won't sit flat on the hub
 
**When:** 2 Nov 2026, step 8
 
**What happened:** I first tried mounting the TMP117 **chip side down**, so the chip would press against the hub, with thermal pad to fill the gap. But the two cable sockets stuck out much further than the chip, and the pad couldn't make up the difference. The board sat on its sockets and the chip didn't touch the hub.
 
**Why:** the STEMMA QT sockets are much taller than the temperature chip.
 
**Fix:** mounted it **back side down** instead, with a bit of thermal pad between the board and the hub, held in place with Kapton tape. Heat reaches the chip through the board rather than directly, so readings respond a little more slowly, but it's good enough for spotting the hub warming up over minutes.
 
---

## 14. ADXL345 shifts on its tape
 
**When:** 2 Nov 2026, step 8
 
**What happened:** the vibration sensor wouldn't stay put on double-sided tape.
 
**Why:** tape is soft and slightly springy, and the fan frame shakes. A sensor that can move adds its own wobble to the readings, and gives different readings each time it settles somewhere new.
 
**Fix:** **superglued** it to the top of the frame. It's also **off-centre**, because the fan's cable loops over the middle of the frame and leaves a bump; a flat mount mattered more than a centred one.
 
---

## 15. Fan rocks front to back
 
**When:** 2 Nov 2026, step 8
 
**What happened:** pushed in the direction of the airflow, the fan rocks slightly in its L-brackets. It doesn't rock side to side.
 
**Why:** each bracket only holds one face of the fan but lifts it off the wooden board. A thin strip of cardboard under the base helps with this space, but doesn't stop the rocking completely.
 
**Decision:** accepted. The models learn what's normal for **this** rig, rocking included. What matters is that the setup stays the same between recordings. Brackets on the front face too would stiffen it, if needed later.
 