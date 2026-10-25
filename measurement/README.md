# Capture tools

These are the Windows physical-input recorder and Steam-launched XInput test application used during the investigation. They record host input data; they do not measure input-to-screen latency.

Build the test application with .NET 10 on Windows:

```powershell
dotnet build measurement/SteamInputOutputTest.csproj -c Release -o measurement/app
```

Add `measurement/app/SteamInputOutputTest.exe` to Steam as a non-Steam shortcut. Enable Steam Input and select the intended test bindings. The application records `XInputGetState` output from inside Steam's game context. Run the Python physical recorder separately, outside Steam, before arming the application:

```powershell
python measurement/capture_windows.py --source hid
# For a physical XInput condition instead:
# python measurement/capture_windows.py --source xinput
```

The recorder waits for a fresh `active-session.json` marker from the test application and shares its QPC clock. Select the verified condition, arm the test, then press A to start. Keep its window in front and follow the prompts. `hid-steam-patch` is a 60-second test; baseline conditions are 120 seconds. The retained `sinput-bridge` label belongs to the earlier bridge experiment and is not required for the direct reader.

Only one matching physical 8BitDo gamepad should be present. The native HID recorder refuses the run if it sees an outside-Steam XInput slot, preventing an extra physical/virtual controller from being mistaken for Steam's translated output. It opens a shared read-only HID handle. Neither physical recorder sends feature, output or firmware commands.

The test application records foreground checks, sampler calls and connection changes. The Python HID recorder timestamps completed host reads. Host buffering, thread scheduling and the chosen API affect the results.

## Saved captures

Published captures use gzip and relative QPC ticks. To rerun the paired direct-reader analysis, copy the JSON metadata from `evidence/direct-steam/` into a new scratch directory and expand its two CSV files there:

```powershell
New-Item -ItemType Directory artifacts/replay
Copy-Item evidence/direct-steam/*.json artifacts/replay/
python tools/unpack_capture.py evidence/direct-steam/windows-hid.csv.gz artifacts/replay/windows-hid.csv
python tools/unpack_capture.py evidence/direct-steam/steam-output.csv.gz artifacts/replay/steam-output.csv
python measurement/analyze_paired.py artifacts/replay
```

`analyze_baseline.py` supports the equivalent metadata/CSV layout for the stock runs. The two XInput captures retain original request labels; use the corrected connection recorded in their exported analysis files. Analysis output should be written in a scratch directory so the committed evidence stays unchanged.
