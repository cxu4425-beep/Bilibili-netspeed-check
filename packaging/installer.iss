; Windows installer for LagScope (Inno Setup 6).
;
; Built in CI after PyInstaller, from packaging/build.py's dist/LagScope.exe:
;   iscc /DAppVersion=3.6 packaging\installer.iss
;
; Deliberately a per-user install: no administrator prompt, no UAC dialog, and
; nothing written outside the user's own profile. That matters for the people
; this tool is for - someone on a school or office machine can still install
; it, and uninstalling really does remove everything the installer put down.
;
; The settings folder (%APPDATA%\LagScope) is left alone on uninstall, because
; it holds the latency history someone may still want. The uninstaller offers
; to remove it instead of deciding for them.

#ifndef AppVersion
  #define AppVersion "0.0"
#endif

#define AppName "LagScope"
#define AppPublisher "LagScope"
#define AppURL "https://github.com/cxu4425-beep/LagScope"
#define AppExeName "LagScope.exe"

[Setup]
AppId={{7B6F1B3E-6C2A-4E2B-9C7E-0D2C4C8B5A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
; Per-user: installs under %LOCALAPPDATA% and never asks for administrator.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist
OutputBaseFilename=LagScope-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; No architecture directives: the payload is a 64-bit exe installed into the
; user's own profile, so there is no 32-bit redirection to opt out of - and
; the spelling of those directives changed between Inno 6 releases.
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
LicenseFile=..\LICENSE
; Windows refuses to replace a running executable, and without these the
; wizard fails halfway through with "DeleteFile failed; code 5" - an error
; that tells the person nothing about what to do. AppMutex makes Setup notice
; the running app *before* it touches any files and ask for it to be closed;
; the app holds this mutex from startup (see src/lagscope/single_instance.py).
AppMutex=LagScope-Running-Mutex
SetupMutex=LagScope-Setup-Mutex
; And if it is still holding files open, close it through Restart Manager
; rather than failing. RestartApplications lets /RESTARTAPPLICATIONS bring it
; back afterwards, which is what the in-app updater relies on.
; "force" rather than "yes": Restart Manager asks an application to close by
; sending its top-level window a close message, and this one is a tray app
; whose window is hidden - so it is never asked, the wait times out, Setup
; proceeds anyway and DeleteFile fails. force terminates what does not answer.
CloseApplications=force
CloseApplicationsFilter=*.exe,*.dll
RestartApplications=yes

; This wizard used to come out in English for everyone, because Chinese only
; became a bundled Inno Setup translation in 6.5 and the CI runner's compiler
; is older - so the "use it if the compiler has it" check silently found
; nothing, every release, and nobody could see why. The files now travel with
; this repository instead of being looked for, which is the only version of
; this that cannot quietly degrade.
;
; Pass /DNoExtraLanguages to build an English-only installer, which is what CI
; falls back to if a translation ever fails to compile: shipping an English
; installer beats shipping none.
#define LangDir AddBackslash(SourcePath) + "languages\"
#ifndef NoExtraLanguages
  #if FileExists(LangDir + "ChineseSimplified.isl")
    #define HaveChineseS
  #endif
  #if FileExists(LangDir + "ChineseTraditional.isl")
    #define HaveChineseT
  #endif
  #if FileExists(LangDir + "Japanese.isl")
    #define HaveJapanese
  #endif
  #if FileExists(LangDir + "Korean.isl")
    #define HaveKorean
  #endif
#endif

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
#ifdef HaveChineseT
Name: "zh_tw"; MessagesFile: "{#LangDir}ChineseTraditional.isl"
#endif
#ifdef HaveChineseS
Name: "zh_cn"; MessagesFile: "{#LangDir}ChineseSimplified.isl"
#endif
#ifdef HaveJapanese
Name: "ja"; MessagesFile: "{#LangDir}Japanese.isl"
#endif
#ifdef HaveKorean
Name: "ko"; MessagesFile: "{#LangDir}Korean.isl"
#endif

[CustomMessages]
en.LaunchAfter=Run {#AppName} now
en.AutoStart=Start {#AppName} when I sign in
en.KeepSettings=Keep my settings and latency history
#ifdef HaveChineseT
zh_tw.LaunchAfter=立即執行 {#AppName}
zh_tw.AutoStart=登入時自動啟動 {#AppName}
zh_tw.KeepSettings=保留設定和延遲歷史紀錄
#endif
#ifdef HaveChineseS
zh_cn.LaunchAfter=立即运行 {#AppName}
zh_cn.AutoStart=登录时自动启动 {#AppName}
zh_cn.KeepSettings=保留设置和延迟历史记录
#endif
#ifdef HaveJapanese
ja.LaunchAfter={#AppName} を今すぐ実行
ja.AutoStart=サインイン時に {#AppName} を起動
ja.KeepSettings=設定と遅延の履歴を残す
#endif
#ifdef HaveKorean
ko.LaunchAfter={#AppName} 지금 실행
ko.AutoStart=로그인할 때 {#AppName} 자동 실행
ko.KeepSettings=설정과 지연 기록 남기기
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutoStart}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; The app manages this key itself from Settings; the task only seeds it.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchAfter}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller's one-file build unpacks beside the exe; nothing else is left.
Type: dirifempty; Name: "{app}"

[Code]
// Windows will not replace a running executable, and the two mechanisms above
// each have a hole:
//
//   * AppMutex only sees versions that create the mutex - which means it can
//     never help someone upgrading *from* a version released before the mutex
//     existed. That is precisely the person hitting the error, so the fix that
//     lives inside the application could not fix the case it was written for.
//   * Restart Manager relies on the application answering a close request,
//     which a tray app with no visible window may never receive.
//
// This one does not care what is running or how old it is.
procedure StopRunningApp;
var
  ResultCode: Integer;
  Attempt: Integer;
begin
  for Attempt := 1 to 2 do
  begin
    // Ask first (no /F sends a close request), then insist. A tray app that
    // exits on its own gets to flush its history file; one that ignores the
    // request loses at most the current minute.
    if Attempt = 1 then
      Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#AppExeName}', '',
           SW_HIDE, ewWaitUntilTerminated, ResultCode)
    else
      Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExeName}', '',
           SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(800);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  StopRunningApp;
end;

// Uninstalling offers to keep the config and the recorded history, rather
// than silently deleting months of measurements or silently leaving them.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  SettingsDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    SettingsDir := ExpandConstant('{userappdata}\{#AppName}');
    if DirExists(SettingsDir) then
    begin
      if MsgBox(ExpandConstant('{cm:KeepSettings}') + #13#10 + SettingsDir,
                mbConfirmation, MB_YESNO) = IDNO then
        DelTree(SettingsDir, True, True, True);
    end;
  end;
end;
