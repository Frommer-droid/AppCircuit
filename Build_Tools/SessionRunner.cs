// Автономный запускатель: шаги сессии дописываются в конец EXE при экспорте.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class SessionRunner
{
    private const string FooterMagic = "APPcircuit-SESS!";
    private const string PayloadMagic = "ACS1DATA";
    private const int MaxPayloadSize = 1024 * 1024;
    private const uint ProcessQueryLimitedInformation = 0x1000;

    private sealed class Step
    {
        internal byte Action;
        internal uint Duration;
        internal string Name;
        internal string Path;
    }

    private sealed class Session
    {
        internal string Name;
        internal List<Step> Steps = new List<Step>();
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint access, bool inheritHandle, int processId);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryFullProcessImageName(
        IntPtr process, int flags, StringBuilder name, ref int size);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            Session session = ReadSession(Process.GetCurrentProcess().MainModule.FileName);
            if (args.Length == 1 && args[0] == "--smoke-test")
                return 0;

            List<string> failures = new List<string>();
            foreach (Step step in session.Steps)
            {
                try
                {
                    RunStep(step);
                }
                catch (Exception error)
                {
                    failures.Add(step.Name + ": " + error.Message);
                }
            }
            if (failures.Count == 0)
                return 0;
            string details = string.Join(Environment.NewLine, failures.ToArray());
            WriteErrorLog(session.Name, details);
            MessageBox.Show(details, "AppCircuit — ошибки запуска сессии",
                MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 1;
        }
        catch (Exception error)
        {
            WriteErrorLog("Загрузка", error.ToString());
            if (args.Length != 1 || args[0] != "--smoke-test")
                MessageBox.Show(error.Message, "AppCircuit — ошибка сессии",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 2;
        }
    }

    private static Session ReadSession(string executablePath)
    {
        using (FileStream file = File.OpenRead(executablePath))
        {
            if (file.Length < 20)
                throw new InvalidDataException("В EXE отсутствуют данные сессии");
            file.Seek(-20, SeekOrigin.End);
            using (BinaryReader footer = new BinaryReader(file, Encoding.UTF8, true))
            {
                uint size = footer.ReadUInt32();
                string marker = Encoding.ASCII.GetString(footer.ReadBytes(16));
                if (marker != FooterMagic || size > MaxPayloadSize || size > file.Length - 20)
                    throw new InvalidDataException("Данные сессии повреждены");
                file.Seek(-(20L + size), SeekOrigin.End);
                byte[] payload = footer.ReadBytes((int)size);
                if (payload.Length != size)
                    throw new InvalidDataException("Данные сессии неполные");
                return DecodeSession(payload);
            }
        }
    }

    private static Session DecodeSession(byte[] payload)
    {
        using (MemoryStream stream = new MemoryStream(payload, false))
        using (BinaryReader reader = new BinaryReader(stream, Encoding.UTF8))
        {
            if (Encoding.ASCII.GetString(reader.ReadBytes(8)) != PayloadMagic)
                throw new InvalidDataException("Неподдерживаемый формат сессии");
            Session session = new Session();
            session.Name = ReadText(reader, stream);
            uint count = reader.ReadUInt32();
            if (count == 0 || count > 10000)
                throw new InvalidDataException("Неверное число шагов сессии");
            for (uint index = 0; index < count; index++)
            {
                Step step = new Step();
                step.Action = reader.ReadByte();
                step.Duration = reader.ReadUInt32();
                step.Name = ReadText(reader, stream);
                step.Path = ReadText(reader, stream);
                if (step.Action < 1 || step.Action > 4 ||
                    (step.Action == 4 && (step.Duration < 1 || step.Duration > 10)) ||
                    (step.Action != 4 && !System.IO.Path.IsPathRooted(step.Path)))
                    throw new InvalidDataException("Неверный шаг сессии");
                session.Steps.Add(step);
            }
            if (stream.Position != stream.Length)
                throw new InvalidDataException("Лишние данные в сессии");
            return session;
        }
    }

    private static string ReadText(BinaryReader reader, Stream stream)
    {
        uint size = reader.ReadUInt32();
        if (size > MaxPayloadSize || size > stream.Length - stream.Position)
            throw new InvalidDataException("Повреждена строка в сессии");
        byte[] data = reader.ReadBytes((int)size);
        if (data.Length != size)
            throw new InvalidDataException("Повреждена строка в сессии");
        return new UTF8Encoding(false, true).GetString(data);
    }

    private static void RunStep(Step step)
    {
        if (step.Action == 4)
        {
            Thread.Sleep(checked((int)step.Duration * 1000));
            return;
        }
        if (step.Action != 2 && !File.Exists(step.Path))
            throw new FileNotFoundException("Файл не найден", step.Path);
        if (step.Action == 3)
        {
            Process.Start(new ProcessStartInfo(step.Path) { UseShellExecute = true });
            return;
        }
        List<int> running = RunningProcessIds(step.Path);
        if (step.Action == 1)
        {
            if (running.Count > 0)
                return;
            Process.Start(new ProcessStartInfo(step.Path)
            {
                WorkingDirectory = System.IO.Path.GetDirectoryName(step.Path),
                UseShellExecute = false
            });
            return;
        }
        foreach (int processId in running)
        {
            using (Process killer = new Process())
            {
                killer.StartInfo = new ProcessStartInfo("taskkill.exe", "/PID " + processId + " /F /T")
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };
                killer.Start();
                killer.WaitForExit();
                if (killer.ExitCode != 0 && killer.ExitCode != 128)
                    throw new InvalidOperationException("Не удалось остановить процесс PID " + processId);
            }
        }
    }

    private static List<int> RunningProcessIds(string targetPath)
    {
        List<int> ids = new List<int>();
        string target = System.IO.Path.GetFullPath(targetPath);
        foreach (Process process in Process.GetProcesses())
        {
            using (process)
            {
                try
                {
                    IntPtr handle = OpenProcess(ProcessQueryLimitedInformation, false, process.Id);
                    if (handle == IntPtr.Zero)
                        continue;
                    try
                    {
                        StringBuilder name = new StringBuilder(32768);
                        int size = name.Capacity;
                        if (QueryFullProcessImageName(handle, 0, name, ref size) &&
                            string.Equals(System.IO.Path.GetFullPath(name.ToString()), target,
                                StringComparison.OrdinalIgnoreCase))
                            ids.Add(process.Id);
                    }
                    finally
                    {
                        CloseHandle(handle);
                    }
                }
                catch (InvalidOperationException) { }
                catch (System.ComponentModel.Win32Exception) { }
                catch (ArgumentException) { }
            }
        }
        return ids;
    }

    private static void WriteErrorLog(string sessionName, string details)
    {
        try
        {
            string directory = System.IO.Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "AppCircuit", "SessionLaunchers");
            Directory.CreateDirectory(directory);
            File.AppendAllText(System.IO.Path.Combine(directory, "errors.log"),
                DateTime.Now.ToString("u") + " [" + sessionName + "] " + details +
                Environment.NewLine, Encoding.UTF8);
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
}
