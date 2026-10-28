#define PublishDirectory GetEnv("STUDY_AGENT_PUBLISH_DIR")
#define OutputDirectory GetEnv("STUDY_AGENT_INSTALLER_OUTPUT")

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

[Icons]
Name: "{autoprograms}\Study Agent"; Filename: "{app}\StudyAgent.Windows.exe"; WorkingDir: "{app}"
