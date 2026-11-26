# CIVI kiosk wiring plan — ESP32 DevKit V1 (30-pin, ESP32-WROOM-32)

This is the plan the firmware will be written for. Wire it exactly like this (or tell us before changing a
pin), then test one part at a time: **speaker → microphone → buttons**.

Unplug the USB cable while you wire. Double-check 3V3 vs VIN before powering on: the microphone must get
**3.3 V**, never 5 V.

## 1. Microphone — INMP441 (I2S input)

| INMP441 pin | ESP32 pin | Note |
|---|---|---|
| VDD | **3V3** | 3.3 V only |
| GND | **GND** | |
| L/R | **GND** | selects the left channel (what the firmware reads) |
| SCK | **D26** (GPIO 26) | bit clock |
| WS | **D25** (GPIO 25) | word select |
| SD | **D33** (GPIO 33) | audio data into the ESP32 |

## 2. Speaker amplifier — MAX98357A (I2S output)

| MAX98357A pin | ESP32 / speaker | Note |
|---|---|---|
| VIN | **VIN** (5 V from USB) | louder than 3.3 V |
| GND | **GND** | |
| BCLK | **D27** (GPIO 27) | bit clock |
| LRC | **D14** (GPIO 14) | word select (a short click at power-on is normal) |
| DIN | **D13** (GPIO 13) | audio data from the ESP32 |
| SD | not connected | amplifier on, mono mix |
| GAIN | not connected | 9 dB gain |
| Speaker + / − | speaker (4–8 Ω, ≤ 3 W) | the two screw terminals |

The microphone and amplifier use the ESP32's **two separate I2S units**, so recording and playback don't share
pins.

## 3. Six buttons (push buttons to GND)

Each button: **one leg to the ESP32 pin, the other leg to GND**. No resistors needed (the firmware turns on the
ESP32's internal pull-up resistors). Order and names follow the handover's six-button arrangement.

| Button | ESP32 pin |
|---|---|
| 1. Language Selector | **D23** (GPIO 23) |
| 2. Confirm | **D22** (GPIO 22) |
| 3. Back | **D21** (GPIO 21) |
| 4. Repeat Voice | **D19** (GPIO 19) |
| 5. Microphone | **D18** (GPIO 18) |
| 6. Visually Challenged | **D4** (GPIO 4) |

All six are on the same side of the board (the side with **3V3** at the end). The microphone and amplifier pins
are all on the other side (the side with **VIN**).

## 4. Status light

The board's built-in blue LED (**D2**, GPIO 2) shows the state; no wiring needed:
on = recording, slow blink = answering, fast blink = no Wi-Fi.

## Pins deliberately not used

| Pins | Why |
|---|---|
| D12, D15, D5, D2 (as input) | "strapping" pins: wrong level at power-on stops the board from booting |
| TX0, RX0 | USB serial (uploading the firmware and the Serial Monitor) |
| D34, D35, VP (36), VN (39) | input-only and without pull-up resistors (buttons would need extra resistors) |
| TX2, RX2 (16, 17) | kept free (not needed) |

## Power

- USB from the laptop powers the ESP32, the microphone (3V3) and the amplifier (VIN).
- A 3 W speaker at full volume can draw more than a laptop USB port gives, which makes the ESP32 restart
  ("brownout"). If that happens, use a 5 V 2 A phone charger or a powered USB hub, or keep the volume moderate.
- All GND pins must be connected together (ESP32, microphone, amplifier, buttons).

## Summary

```
                 ESP32 DevKit V1 (30-pin)
   INMP441 SD  -> D33        D23 <- Language
   INMP441 WS  -> D25        D22 <- Confirm
   INMP441 SCK -> D26        D21 <- Back
   AMP BCLK    <- D27        D19 <- Repeat Voice
   AMP LRC     <- D14        D18 <- Microphone
   AMP DIN     <- D13        D4  <- Visually Challenged
   AMP VIN     <- VIN        3V3 -> INMP441 VDD
   all GND     -- GND        GND -- all GND, INMP441 L/R, buttons' other legs
```
