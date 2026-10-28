#define MsixPath GetEnv("STUDY_AGENT_MSIX")
#define OutputDirectory GetEnv("STUDY_AGENT_INSTALLER_OUTPUT")

[Setup]
AppId={{A6D533F4-96F9-4F91-810B-5721FF5A86CA}
AppName=Study Agent
AppVersion=1.0.9
AppPublisher=Study Agent contributors
DefaultDirName={tmp}\StudyAgentInstaller
DisableDirPage=yes
DisableProgramGroupPage=yes
Uninstallable=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir={#OutputDirectory}
OutputBaseFilename=StudyAgentSetup
Compression=none
SolidCompression=no
WizardStyle=modern
SetupLogging=yes

[Files]
Source: "{#MsixPath}"; DestDir: "{tmp}"; DestName: "StudyAgent.msix"; Flags: dontcopy

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  PackagePath: String;
  Parameters: String;
begin
  Result := '';
  try
    ExtractTemporaryFile('StudyAgent.msix');
  except
    Result := 'Could not extract the Study Agent MSIX package.';
    Exit;
  end;

  PackagePath := ExpandConstant('{tmp}\StudyAgent.msix');
  Parameters := '-NoProfile -ExecutionPolicy Bypass -Command "try { Add-AppxPackage -Path ' + #39 + PackagePath + #39 + ' -AllowUnsigned -ErrorAction Stop } catch { Write-Error $_; exit 1 }"';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Parameters, '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := 'Could not start PowerShell to install the application.';
    Exit;
  end;

  if ResultCode <> 0 then
    Result := 'Windows could not install the MSIX package. See the PowerShell error window and try again.';
end;
