#define PublishDirectory GetEnv("STUDY_AGENT_PUBLISH_DIR")
#define OutputDirectory GetEnv("STUDY_AGENT_INSTALLER_OUTPUT")
#define WebViewBootstrapper GetEnv("STUDY_AGENT_WEBVIEW_BOOTSTRAPPER")

[Setup]
AppId={{A6D533F4-96F9-4F91-810B-5721FF5A86CA}
AppName=Study Agent
AppVersion=1.0.9
AppPublisher=Study Agent contributors
DefaultDirName={localappdata}\Programs\Study Agent
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDirectory}
OutputBaseFilename=StudyAgentSetup
Compression=none
SolidCompression=no
WizardStyle=modern
SetupLogging=yes

[Files]
Source: "{#PublishDirectory}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#WebViewBootstrapper}"; DestDir: "{tmp}"; DestName: "WebView2Setup.exe"; Flags: dontcopy

[Icons]
Name: "{autoprograms}\Study Agent"; Filename: "{app}\StudyAgent.Windows.exe"; WorkingDir: "{app}"

[Code]
function WebView2Available: Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := (RegQueryStringValue(HKLM32, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU32, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU64, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if WebView2Available then Exit;
  try
    ExtractTemporaryFile('WebView2Setup.exe');
  except
    Result := 'Could not extract the WebView2 installer.';
    Exit;
  end;
  if not Exec(ExpandConstant('{tmp}\WebView2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    Result := 'Could not start the Microsoft WebView2 installer.'
  else if (ExitCode <> 0) or not WebView2Available then
    Result := 'WebView2 could not be installed. Connect to the internet and retry (error ' + IntToStr(ExitCode) + ').';
end;
