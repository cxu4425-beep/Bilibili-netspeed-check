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
CloseApplications=yes
RestartApplications=no

; Chinese is an unofficial Inno Setup translation, so it is present in some
; installs of the compiler and not others - including on CI runners. Requiring
; it would mean no installer at all on a machine that lacks it, so it is used
; when available and the wizard falls back to English when it is not. The app
; itself is unaffected: it picks its own language on first run.
#define ChineseIsl "Languages\ChineseSimplified.isl"
#define JapaneseIsl "Languages\Japanese.isl"
#define KoreanIsl "Languages\Korean.isl"
#if FileExists(AddBackslash(CompilerPath) + ChineseIsl)
  #define HaveChinese
#endif
#if FileExists(AddBackslash(CompilerPath) + JapaneseIsl)
  #define HaveJapanese
#endif
#if FileExists(AddBackslash(CompilerPath) + KoreanIsl)
  #define HaveKorean
#endif

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
#ifdef HaveChinese
Name: "zh"; MessagesFile: "compiler:{#ChineseIsl}"
#endif
#ifdef HaveJapanese
Name: "ja"; MessagesFile: "compiler:{#JapaneseIsl}"
#endif
#ifdef HaveKorean
Name: "ko"; MessagesFile: "compiler:{#KoreanIsl}"
#endif

[CustomMessages]
en.LaunchAfter=Run {#AppName} now
en.AutoStart=Start {#AppName} when I sign in
en.KeepSettings=Keep my settings and latency history
#ifdef HaveChinese
zh.LaunchAfter=立即运行 {#AppName}
zh.AutoStart=登录时自动启动 {#AppName}
zh.KeepSettings=保留设置和延迟历史记录
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
