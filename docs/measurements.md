# Measurements

All recorded input timing uses Windows QueryPerformanceCounter. Timestamps in the exported CSVs have been shifted by each session's start timestamp; interval timing is preserved. Frequency is stored in each request file. The receiver-only motion fixture uses its first report as zero. Device serials, local paths, process identifiers and USB history are excluded.

## Stock comparison

One completed recording was retained for each available connection: wireless XInput, wired XInput and wireless native HID. Each lasted two minutes. Windows physical input was captured outside Steam; a diagnostic launched through Steam captured its game-facing XInput output on the same host clock.

Both XInput runs originally had `xinput-wired` in their request labels. Saved USB connection history established that the first was wireless and the second wired. Original labels are retained in the analysis metadata; export directory names use the corrected connections. The wired run lost focus at approximately 111 seconds, during its final idle phase. Movement/button phases occurred before that change. Aborted attempts and the separate short button sequence are excluded from stick statistics.

| Connection | Windows distinct LX / LY / RX / RY | Steam distinct LX / LY / RX / RY |
| --- | --- | --- |
| Wireless XInput | 13,376 / 13,378 / 15,370 / 15,482 | 8,325 / 8,380 / 9,695 / 9,797 |
| Wired XInput | 15,618 / 15,081 / 17,792 / 18,303 | 9,602 / 9,348 / 11,231 / 11,629 |
| Wireless native HID | 255 / 256 / 255 / 256 | 255 / 256 / 255 / 256 |

The native recording contained 119,982 physical HID reports, approximately 1,000.03 report arrivals/sec, median interval 0.9996 ms. The raw descriptor exposed four 8-bit axes. All Steam values fit the scaled-byte grid, including center handling, Y inversion and endpoint clamping.

During the stock circle phases, the observed changed-stick-state rates were approximately:

| Connection | Windows changes/sec | Steam changes/sec |
| --- | ---: | ---: |
| Wireless XInput | 838 | 448 |
| Wired XInput | 875 | 465 |
| Wireless native HID | 658 | 395 |

These rates depend on the movement and host sampling. The Windows XInput probe polls an API rather than observing USB transactions. The Steam configuration query returned `controller_rate=2000` microseconds, corresponding to an active 500 Hz processing interval. That setting is not a universal Steam ceiling or a measured end-to-end latency.

The native extra controls were identified through an ordered PL, PR, L4, R4 sequence followed by ordinary buttons. Windows reported usages 6, 3, 17 and 18. Steam had separate controls for all four. Wired native HID was not exposed through the tested normal USB connection/mode procedure.

## Receiver extension

The modified receiver's motion capture contained 45,252 reports over approximately 45.25 seconds. All original byte axes agreed with the preserved conversion on every report. The added source words produced 11,848 / 11,966 / 14,034 / 12,980 distinct values. All four words reached 0 and 65535, and each used all 256 low-byte values.

Native report arrivals remained approximately 1,000.03/sec. The busiest second contained 845 changed fine stick states. The receiver patch changed report packing, not the report timer.

Wireless XInput was checked afterward. All axes reached -32768..32767, both triggers reached 0 and 255, and A/B produced their expected masks. A physical receiver/controller power cycle retained the fine fields. This was a functional regression check, not a latency or battery test.

## Direct Steam path

The 60-second paired recording used the patched receiver and patched Steam reader. The bridge process was stopped, its virtual device removed, and HidHide disabled. Outside Steam, no XInput slot was present. The Steam-launched tester received slot 0 through Steam's translation of physical `2DC8:6012`.

There were 59,969 physical reports; the recorder attached approximately 33 ms after the shared start marker. Average arrival rate was 1,000.025/sec and median interval 0.9993 ms. The tester remained in the foreground throughout; there were no disconnects.

| Axis | Legacy codes | Physical fine codes | Steam output codes |
| --- | ---: | ---: | ---: |
| LX | 255 | 10,658 | 6,554 |
| LY | 256 | 10,656 | 6,469 |
| RX | 255 | 11,506 | 6,910 |
| RY | 256 | 11,736 | 7,120 |

Steam outputs reached -32767..32767 and included adjacent codes one unit apart. In the circle phase, approximately 788 changed physical states/sec and 424 changed Steam states/sec were observed. Both triggers reached 0 and 255.

Diagnostic bindings were PL -> left-stick click (`0x40`), PR -> right-stick click (`0x80`), L4 -> View (`0x20`), R4 -> Start (`0x10`). Each was pressed twice and matched its separate output. A/B checks also passed. These bindings were confined to the diagnostic shortcut; existing game layouts were retained.

## Offline parser validation

The original and patched DLLs were executed separately against synthetic reports and the 45,252-report physical fixture. The candidate passed 262,144 exhaustive fine-axis cases, 4,096 fallback cases and 256 wrong-PID cases. Buttons, hat and triggers matched expected outputs. With the extension cleared, original and candidate replay digests matched:

```text
000c2d5250ef60e8c39471fad6b834abc987b901d90b5d8bd0ba6cfd424d2b71
```

Receiver instruction-model tests covered all 65,536 values independently on each axis and 10,000 deterministic coupled states. The model checked fine word stores, preserved legacy/guard bytes and inspected live registers. It is a bounded instruction model; it does not emulate the full firmware or establish timing behavior.

## Witcher 3 observation

The published snapshot covers 3,159.7326743 seconds and 3,159,783 physical HID reports. The recording continued after this snapshot; these figures describe only the analyzed interval.

| Measurement | Value |
| --- | ---: |
| Average report arrival rate | 1,000.0156/sec |
| Median read interval | 0.9994 ms |
| 95th percentile | 1.0391 ms |
| 99th percentile | 1.0895 ms |
| Largest interval | 16.7893 ms |
| Intervals over 5 ms | 3 |
| Malformed reports | 0 |
| Fine/legacy axis mismatches | 0 |

The three long reads were 16.7893, 8.7562 and 8.7396 ms, within approximately 0.2 seconds around minute 38. The affected one-second buckets contained 978 and 993 reports. Each gap was followed by one short read and then roughly 1 ms reads. The cause cannot be assigned from this capture. It does not show that every delayed report was recovered or establish radio packet loss.

Fine code counts were 53,519 / 53,694 / 55,536 / 41,162. There were 647,895 adjacent fine stick changes, including 321,457 while all four legacy byte axes stayed unchanged. Both triggers used all 256 byte values. No independent PL/PR/L4/R4 press edges were recorded in this interval, so it does not retest paddle delivery to the game.

The read handle remained active. Steam's during-session log showed application binding activations and no controller disconnect/reconnect entries. All 3,095 process samples contained Witcher and none contained the bridge. The installed patched reader hash was rechecked successfully.

## Limits

Only one physical pair was tested. Counts depend on movement coverage, firmware shaping and sampling. Neither 16-bit fields nor tens of thousands of observed codes establish independently accurate physical positions.

Host HID read timing includes Windows scheduling and buffering. It is not USB-bus timing or input-to-screen latency. The paired diagnostic captured Steam's game-facing output; the Witcher monitor captured receiver reports and process/log context, without intercepting Witcher's input calls. Rumble output, motion controls, battery consumption and long-term failure rates were not measured.

The earlier software bridge demonstrated another host path but was not used in the direct-reader or published gameplay measurements. Comparisons between separate manual movement runs cannot establish that one route has better latency or precision.
