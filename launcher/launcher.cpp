// 纯原生启动器：找 Python，准备依赖，启动 pywebview 壳。
#include <windows.h>
#include <shellapi.h>
#include <urlmon.h>
#include <wintrust.h>
#include <softpub.h>

#include <string>
#include <vector>

#pragma comment(lib, "user32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "urlmon.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "wintrust.lib")

namespace {

std::wstring Quote(const std::wstring& value) {
    return L"\"" + value + L"\"";
}

bool Exists(const std::wstring& path) {
    const DWORD attr = GetFileAttributesW(path.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY);
}

std::wstring DirectoryOf(const std::wstring& path) {
    const size_t pos = path.find_last_of(L"\\/");
    return pos == std::wstring::npos ? L"." : path.substr(0, pos);
}

std::wstring Join(const std::wstring& a, const std::wstring& b) {
    if (a.empty()) return b;
    if (a.back() == L'\\' || a.back() == L'/') return a + b;
    return a + L"\\" + b;
}

std::wstring ModuleDirectory() {
    std::vector<wchar_t> buffer(MAX_PATH);
    for (;;) {
        const DWORD size = GetModuleFileNameW(nullptr, buffer.data(),
                                              static_cast<DWORD>(buffer.size()));
        if (size == 0) return L".";
        if (size < buffer.size()) {
            return DirectoryOf(buffer.data());
        }
        buffer.resize(buffer.size() * 2);
    }
}

std::wstring FindOnPath(const wchar_t* name) {
    wchar_t buffer[MAX_PATH];
    const DWORD size = SearchPathW(nullptr, name, nullptr, MAX_PATH, buffer, nullptr);
    return size > 0 && size < MAX_PATH ? std::wstring(buffer, size) : L"";
}

std::wstring Env(const wchar_t* name) {
    const DWORD size = GetEnvironmentVariableW(name, nullptr, 0);
    if (size == 0) return L"";
    std::vector<wchar_t> buffer(size);
    GetEnvironmentVariableW(name, buffer.data(), size);
    return std::wstring(buffer.data());
}

bool RunAndWait(const std::wstring& command, const std::wstring& cwd, DWORD& code) {
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    std::vector<wchar_t> mutableCommand(command.begin(), command.end());
    mutableCommand.push_back(L'\0');
    if (!CreateProcessW(nullptr, mutableCommand.data(), nullptr, nullptr, FALSE,
                        CREATE_NO_WINDOW, nullptr, cwd.c_str(), &startup, &process)) {
        return false;
    }
    WaitForSingleObject(process.hProcess, INFINITE);
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return true;
}

struct PythonPaths {
    std::wstring console;
    std::wstring windowed;
};

bool LocatePython(PythonPaths& paths) {
    const std::wstring envConsole = Env(L"AI_AGENT_PYTHON");
    const std::wstring envWindowed = Env(L"AI_AGENT_PYTHONW");
    if (!envConsole.empty() && Exists(envConsole)) {
        paths.console = envConsole;
        paths.windowed = envWindowed.empty() ? envConsole : envWindowed;
        return true;
    }
    paths.console = FindOnPath(L"python.exe");
    if (paths.console.empty()) return false;
    paths.windowed = FindOnPath(L"pythonw.exe");
    if (paths.windowed.empty()) {
        const std::wstring candidate = Join(DirectoryOf(paths.console), L"pythonw.exe");
        if (Exists(candidate)) paths.windowed = candidate;
    }
    return !paths.windowed.empty();
}

bool WebView2Installed() {
    const wchar_t* paths[] = {
        L"C:\\Program Files (x86)\\Microsoft\\EdgeWebView\\Application",
        L"C:\\Program Files\\Microsoft\\EdgeWebView\\Application",
    };
    for (const auto* path : paths) {
        const DWORD attr = GetFileAttributesW(path);
        if (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY)) {
            return true;
        }
    }
    return false;
}

bool VerifyAuthenticode(const std::wstring& path) {
    WINTRUST_FILE_INFO file_info{};
    file_info.cbStruct = sizeof(file_info);
    file_info.pcwszFilePath = path.c_str();

    WINTRUST_DATA data{};
    data.cbStruct = sizeof(data);
    data.dwUIChoice = WTD_UI_NONE;
    data.fdwRevocationChecks = WTD_REVOKE_NONE;
    data.dwUnionChoice = WTD_CHOICE_FILE;
    data.pFile = &file_info;
    data.dwStateAction = WTD_STATEACTION_VERIFY;

    GUID policy = WINTRUST_ACTION_GENERIC_VERIFY_V2;
    const LONG status = WinVerifyTrust(nullptr, &policy, &data);
    data.dwStateAction = WTD_STATEACTION_CLOSE;
    WinVerifyTrust(nullptr, &policy, &data);
    return status == ERROR_SUCCESS;
}

bool InstallWebView2() {
    wchar_t temp[MAX_PATH];
    const DWORD size = GetTempPathW(MAX_PATH, temp);
    if (size == 0) return false;
    const std::wstring installer = Join(temp, L"MicrosoftEdgeWebView2Setup.exe");
    DeleteFileW(installer.c_str());
    const HRESULT hr = URLDownloadToFileW(
        nullptr, L"https://go.microsoft.com/fwlink/p/?LinkId=2124703",
        installer.c_str(), 0, nullptr);
    if (FAILED(hr) || !Exists(installer)) return false;
    if (!VerifyAuthenticode(installer)) {
        DeleteFileW(installer.c_str());
        return false;
    }
    SHELLEXECUTEINFOW info{};
    info.cbSize = sizeof(info);
    info.fMask = SEE_MASK_NOCLOSEPROCESS;
    info.lpFile = installer.c_str();
    info.lpParameters = L"/silent /install";
    info.nShow = SW_HIDE;
    if (!ShellExecuteExW(&info) || info.hProcess == nullptr) return false;
    WaitForSingleObject(info.hProcess, 120000);
    CloseHandle(info.hProcess);
    return WebView2Installed();
}

int Fail(const std::wstring& message) {
    MessageBoxW(nullptr, message.c_str(), L"AI Agent", MB_ICONERROR | MB_OK);
    return 1;
}

}  // namespace

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    const HANDLE mutex = CreateMutexW(nullptr, TRUE, L"Local\\AIAgent.Gui");
    if (mutex == nullptr) return Fail(L"无法创建单实例锁。");
    if (GetLastError() == ERROR_ALREADY_EXISTS) return 0;

    const std::wstring root = ModuleDirectory();
    if (!Exists(Join(root, L"agent\\gui\\launcher.py"))) {
        return Fail(L"项目文件不完整：缺少 agent\\gui\\launcher.py。");
    }

    PythonPaths python;
    if (!LocatePython(python)) {
        return Fail(L"未找到 Python。\n请安装 Python 3.10+，并勾选 Add Python to PATH。");
    }

    if (!WebView2Installed() && !InstallWebView2()) {
        return Fail(L"缺少 WebView2 Runtime，自动安装失败。\n请手动安装 Microsoft Edge WebView2 Runtime。");
    }

    DWORD code = 0;
    const std::wstring bootstrap =
        Quote(python.console) + L" -m agent.gui.bootstrap";
    if (!RunAndWait(bootstrap, root, code) || code != 0) {
        return Fail(L"pywebview 依赖准备失败。\n请检查网络或 Python 的 pip。");
    }

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    const std::wstring command =
        Quote(python.windowed) + L" -m agent.gui.launcher";
    std::vector<wchar_t> mutableCommand(command.begin(), command.end());
    mutableCommand.push_back(L'\0');
    if (!CreateProcessW(nullptr, mutableCommand.data(), nullptr, nullptr, FALSE,
                        CREATE_NO_WINDOW, nullptr, root.c_str(), &startup, &process)) {
        return Fail(L"启动 Python 壳失败。");
    }

    const HANDLE job = CreateJobObjectW(nullptr, nullptr);
    if (job != nullptr) {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                &info, sizeof(info));
        AssignProcessToJobObject(job, process.hProcess);
    }

    WaitForSingleObject(process.hProcess, INFINITE);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    if (job != nullptr) CloseHandle(job);
    CloseHandle(mutex);
    return 0;
}
