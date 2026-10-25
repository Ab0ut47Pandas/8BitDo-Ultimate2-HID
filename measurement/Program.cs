using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;

internal static class Program
{
    [STAThread] static void Main() { ApplicationConfiguration.Initialize(); Application.Run(new OutputTest()); }
}

internal sealed class OutputTest : Form
{
    [StructLayout(LayoutKind.Sequential)] struct Pad
    { public ushort Buttons; public byte LT, RT; public short LX, LY, RX, RY; }
    [StructLayout(LayoutKind.Sequential)] struct State { public uint Packet; public Pad Pad; }
    [DllImport("xinput1_4.dll")] static extern uint XInputGetState(uint slot, out State state);
    [DllImport("user32.dll")] static extern nint GetForegroundWindow();

    bool ShortProtocolTest => conditionName is "sinput-bridge" or "hid-steam-patch";
    int CaptureSeconds => ShortProtocolTest ? 60 : 120;
    readonly Label status = new() { Dock = DockStyle.Fill, Font = new Font("Consolas", 12), Padding = new Padding(16) };
    readonly ComboBox condition = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 210 };
    readonly NumericUpDown repetition = new() { Minimum = 1, Maximum = 10, Value = 1, Width = 55 };
    readonly Button arm = new() { Text = "Arm; press A to start", AutoSize = true };
    readonly Button stop = new() { Text = "Stop and save partial", AutoSize = true, Enabled = false };
    readonly System.Windows.Forms.Timer timer = new() { Interval = 100 };
    readonly string root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, ".."));
    volatile bool running = true, armed, recording, stopRequested, saving;
    string conditionName = "xinput-wired", message = "Choose the verified connection and mode, then arm the recorder.";
    int runNumber = 1;
    long captureStart;
    nint ownWindow;
    string? lastArmRequest;

    public OutputTest()
    {
        Text = "Steam Input Output Test"; ClientSize = new Size(900, 570); StartPosition = FormStartPosition.CenterScreen;
        condition.Items.AddRange(new object[] { "xinput-wired", "xinput-wireless", "hid-wired", "hid-wireless", "sinput-bridge", "hid-steam-patch" });
        condition.SelectedIndex = 0;
        var controls = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 55, Padding = new Padding(8) };
        controls.Controls.Add(condition); controls.Controls.Add(new Label { Text = "Run", AutoSize = true });
        controls.Controls.Add(repetition); controls.Controls.Add(arm); controls.Controls.Add(stop);
        Controls.Add(status); Controls.Add(controls); ownWindow = Handle;
        arm.Click += (_, _) =>
        {
            Arm();
        };
        stop.Click += (_, _) => { stopRequested = true; armed = false; };
        timer.Tick += (_, _) =>
        {
            CheckArmRequest();
            status.Text = message;
            bool idle = !armed && !recording && !saving;
            arm.Enabled = condition.Enabled = repetition.Enabled = idle; stop.Enabled = !idle;
        };
        timer.Start();
        Directory.CreateDirectory(Path.Combine(root, "sessions"));
        var worker = new Thread(Sample) { IsBackground = true, Name = "Read-only Steam output sampler" };
        FormClosed += (_, _) => { running = false; timer.Stop(); worker.Join(2000); };
        worker.Start();
    }

    void Arm()
    {
        if (armed || recording || saving) return;
        conditionName = condition.Text; runNumber = (int)repetition.Value;
        stopRequested = false; armed = true;
        condition.Enabled = repetition.Enabled = arm.Enabled = false; stop.Enabled = true;
    }

    void CheckArmRequest()
    {
        string path = Path.Combine(root, "bridge-arm.json");
        if (!File.Exists(path) || armed || recording || saving) return;
        try
        {
            using var request = JsonDocument.Parse(File.ReadAllText(path));
            var r = request.RootElement;
            string? id = r.GetProperty("request_id").GetString();
            string? requestedCondition = r.GetProperty("condition").GetString();
            if (id == lastArmRequest || requestedCondition is not ("sinput-bridge" or "hid-steam-patch")) return;
            DateTime created = r.GetProperty("created_utc").GetDateTime().ToUniversalTime();
            if (Math.Abs((DateTime.UtcNow-created).TotalSeconds) > 120) return;
            lastArmRequest = id;
            condition.SelectedItem = requestedCondition;
            repetition.Value = Math.Clamp(r.GetProperty("repetition").GetInt32(), 1, 10);
            Arm();
            File.WriteAllText(Path.Combine(root,"bridge-arm-ack.json"),JsonSerializer.Serialize(new {request_id=id,armed,utc=DateTime.UtcNow}));
        }
        catch (IOException) { }
        catch (JsonException) { }
    }

    object Context()
    {
        var p = Process.GetCurrentProcess();
        var modules = p.Modules.Cast<ProcessModule>()
            .Where(m => m.ModuleName.Contains("xinput", StringComparison.OrdinalIgnoreCase) || m.ModuleName.Contains("GameOverlayRenderer", StringComparison.OrdinalIgnoreCase))
            .Select(m => new { name = m.ModuleName, path = m.FileName, version = m.FileVersionInfo.FileVersion }).ToArray();
        return new { process = p.Id, steam_app_id = Environment.GetEnvironmentVariable("SteamAppId"),
            steam_game_id = Environment.GetEnvironmentVariable("SteamGameId"), modules,
            qpc_frequency = Stopwatch.Frequency, utc = DateTime.UtcNow,
            note = "Read-only XInputGetState. Verify Steam emulation separately, especially when the physical controller itself is XInput. Overlay presence alone is insufficient." };
    }

    string Phase(double seconds) => ShortProtocolTest ? seconds switch
    {
        < 5 => "Release everything; leave both sticks centered.",
        < 20 => "Both sticks: slow full horizontal sweeps, then vertical sweeps.",
        < 35 => "Both sticks: large circles, then smaller circles near the center.",
        < 42 => "Slowly squeeze and release each trigger separately.",
        < 56 => "Press PL, PR, L4, R4, then A and B separately, two seconds apart.",
        _ => "Release everything; leave both sticks centered."
    } : seconds switch
    {
        < 10 => "Release everything; leave the sticks centered.",
        < 30 => "Left stick: slow full horizontal sweeps, then vertical sweeps.",
        < 50 => "Right stick: slow full horizontal sweeps, then vertical sweeps.",
        < 70 => "Both sticks: large circles, then smaller circles near the center.",
        < 85 => "Slowly squeeze and release each trigger separately.",
        < 105 => "Press PL, PR, L4, R4 separately, then normal buttons and D-pad.",
        _ => "Release everything; leave the sticks centered."
    };

    void Sample()
    {
        var last = new State[4]; var have = new bool[4]; var counts = new int[4];
        var disconnects = new int[4]; var firstConnected = new bool[4];
        var values = Enumerable.Range(0,4).Select(_ => Enumerable.Range(0,4).Select(_ => new HashSet<short>()).ToArray()).ToArray();
        StreamWriter? csv = null; string? folder = null;
        long next = Stopwatch.GetTimestamp(), iterations = 0, lastFlush = 0;
        bool aReleased = false; double finalElapsed = 0;
        long focusSamples = 0, foregroundSamples = 0;
        try
        {
            while (running)
            {
                long now = Stopwatch.GetTimestamp();
                var current = new State[4]; var connected = new bool[4]; bool anyA = false;
                for (uint slot = 0; slot < 4; slot++)
                {
                    connected[slot] = XInputGetState(slot,out current[slot]) == 0;
                    anyA |= connected[slot] && (current[slot].Pad.Buttons & 0x1000) != 0;
                }
                if (!armed) aReleased = false;
                if (armed && !anyA) aReleased = true;
                if (armed && aReleased && anyA)
                {
                    armed = false; recording = true; aReleased = false; captureStart = now;
                    folder = Path.Combine(root,"sessions",$"{DateTime.Now:yyyyMMdd-HHmmss-fff}-{conditionName}-r{runNumber}");
                    Directory.CreateDirectory(folder);
                    csv = new StreamWriter(Path.Combine(folder,"steam-output.csv"));
                    csv.WriteLine("qpc_ticks,slot,connected,packet,buttons,lx,ly,rx,ry,lt,rt");
                    Array.Clear(have); Array.Clear(counts); Array.Clear(disconnects); Array.Copy(connected,firstConnected,4);
                    foreach (var slot in values) foreach (var axis in slot) axis.Clear();
                    iterations = focusSamples = foregroundSamples = 0; lastFlush = now; finalElapsed = 0;
                    var request = new { schema = 1, session = folder, condition = conditionName, repetition = runNumber,
                        start_qpc = now, stop_qpc = now + CaptureSeconds*Stopwatch.Frequency,
                        qpc_frequency = Stopwatch.Frequency, utc = DateTime.UtcNow };
                    File.WriteAllText(Path.Combine(folder,"request.json"),JsonSerializer.Serialize(request,new JsonSerializerOptions {WriteIndented=true}));
                    File.WriteAllText(Path.Combine(folder,"steam-context.json"),JsonSerializer.Serialize(Context(),new JsonSerializerOptions {WriteIndented=true}));
                    string marker = Path.Combine(root,"active-session.json");
                    File.WriteAllText(marker+".tmp",JsonSerializer.Serialize(request)); File.Move(marker+".tmp",marker,true);
                }
                var lines = new List<string>();
                for (int slot = 0; slot < 4; slot++)
                {
                    State s = current[slot]; Pad p = s.Pad;
                    if (connected[slot]) lines.Add($"Slot {slot}: LX {p.LX,7} LY {p.LY,7} RX {p.RX,7} RY {p.RY,7} LT {p.LT,3} RT {p.RT,3}");
                    if (!recording) continue;
                    if (connected[slot])
                    { values[slot][0].Add(p.LX); values[slot][1].Add(p.LY); values[slot][2].Add(p.RX); values[slot][3].Add(p.RY); }
                    if ((!have[slot] && connected[slot]) || have[slot] != connected[slot] ||
                        (connected[slot] && (!p.Equals(last[slot].Pad) || s.Packet != last[slot].Packet)))
                    {
                        csv!.WriteLine($"{now},{slot},{(connected[slot]?1:0)},{s.Packet},{p.Buttons},{p.LX},{p.LY},{p.RX},{p.RY},{p.LT},{p.RT}");
                        counts[slot]++; if (have[slot] && !connected[slot]) disconnects[slot]++;
                    }
                    have[slot] = connected[slot]; last[slot] = s;
                }
                double elapsed = recording ? (now-captureStart)/(double)Stopwatch.Frequency : 0;
                if (recording)
                {
                    iterations++; finalElapsed = elapsed;
                    if (now-lastFlush >= Stopwatch.Frequency/10)
                    { csv!.Flush(); lastFlush = now; focusSamples++; if (GetForegroundWindow() == ownWindow) foregroundSamples++; }
                }
                message = "STEAM GAME-FACING OUTPUT TEST\n\n" + (lines.Count==0 ? "No XInput controller visible to this process." : string.Join("\n",lines))
                    + "\n\n" + (recording ? $"{conditionName}, run {runNumber}: {elapsed:F1} / {CaptureSeconds} seconds\n\n{Phase(elapsed)}" :
                        armed ? "ARMED: release A, then press A when ready. There is no countdown." : "Choose the verified condition, arm, then press A when ready.")
                    + $"\n\nSteamAppId: {Environment.GetEnvironmentVariable("SteamAppId")??"none"}"
                    + "\nKeep this window in front during the capture."
                    + "\nRead-only. Changed-state counts are not physical latency or USB polling measurements.";
                if (recording && (elapsed>=CaptureSeconds || stopRequested)) SaveSummary(elapsed>=CaptureSeconds ? "complete" : "stopped");
                if (recording)
                {
                    next = Math.Max(next+Stopwatch.Frequency/4000,now);
                    while (running && Stopwatch.GetTimestamp()<next) Thread.SpinWait(20);
                }
                else { Thread.Sleep(5); next = Stopwatch.GetTimestamp(); }
            }
        }
        catch (Exception e) { message=e.ToString(); File.WriteAllText(Path.Combine(root,"error.txt"),e.ToString()); }
        finally { if (csv!=null) SaveSummary("interrupted"); }

        void SaveSummary(string outcome)
        {
            saving=true; recording=false; csv?.Dispose(); csv=null;
            if (folder==null) { saving=false; return; }
            var result = new { outcome, condition=conditionName, repetition=runNumber, seconds=finalElapsed,
                sampler_iterations=iterations, sampler_target_hz=4000, context=Context(),
                foreground_checks=focusSamples, foreground_matches=foregroundSamples,
                slots=Enumerable.Range(0,4).Select(i=>new {slot=i,initially_connected=firstConnected[i],changed_rows=counts[i],disconnects=disconnects[i],
                    axes=values[i].Select((v,j)=>new {axis=new[]{"lx","ly","rx","ry"}[j],unique=v.Count,
                        min=v.Count>0?(int?)v.Min():null,max=v.Count>0?(int?)v.Max():null}).ToArray()}).ToArray() };
            File.WriteAllText(Path.Combine(folder,"steam-summary.json"),JsonSerializer.Serialize(result,new JsonSerializerOptions {WriteIndented=true}));
            File.WriteAllText(Path.Combine(folder,"finished.json"),JsonSerializer.Serialize(new {outcome,stop_qpc=Stopwatch.GetTimestamp()}));
            stopRequested=false; saving=false;
        }
    }
}
