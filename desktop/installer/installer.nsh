# The words the Windows installer and uninstaller show, in plain language.
#
# electron-builder's NSIS wizard ships with generic setup wording: "Choose
# Installation Options", "Please select whether you wish to make this
# software available...", "per-machine", "Click OK", "Failed to decompress
# files". Axcess's interface follows docs/plain-language.md (the main point
# first, short sentences, "you", everyday words, no "please", messages that
# say what happened and what to do), and WCAG 2.2 SC 3.1.5 Reading Level
# (Level AAA), which this repo meets. The installer is part of that
# interface, so this file replaces every string a person can see or hear in
# the wizard, its message boxes and the uninstaller.
#
# How: electron-builder.config.cjs names this file as `nsis.include`, and
# the customHeader macro below runs after the languages load, in both the
# installer and the uninstaller build. A LangString set twice keeps the
# last value; NSIS warns (6030) and the build treats warnings as errors, so
# the warning is off for this block only. Checked with makensis 3.0.4.1:
# the built exe holds the new text and not the old.
#
# Limits kept in mind:
# - Page titles fit one line, subtitles two, and the text above the "who
#   to install for" choices two (a 300 by 20 dialog-unit label).
# - Message boxes have the buttons Windows gives them (OK, Cancel, Retry),
#   so the text names those buttons rather than a verb of our own.
# - Keyboard shortcut letters (the & in "Only for &me") are kept, and none
#   clash with Back, Next or Cancel on the same page.
# - The note under the two choices changes when you pick one. Windows does
#   not read that change aloud, so the admin-password fact is also in the
#   text above the choices, which is read with the page.
# - "Administrator permission", not "password": an administrator account
#   only confirms in the Windows prompt; other accounts type a password.
# - Two messages are hard-coded in English in electron-builder's template
#   and cannot be changed here: "Logon service not running, aborting!" and
#   "Unable to elevate, error <code>". Both show only when Windows cannot
#   ask for an administrator password.
# Standard wizard buttons (Back, Next, Install, Browse, Cancel, Finish,
# Uninstall) keep their Windows names: people know them from other setups,
# and Windows Settings uses "Uninstall" for the same action (W3C COGA,
# "Making Content Usable": the same word for the same thing,
# https://www.w3.org/TR/coga-usable/).

# The footer ("Axcess 0.61", bottom left). MUI draws it with two controls
# in the branding grey: 1028 disabled, 1256 coloured /BRANDING, #a0a0a0 on
# #f0f0f0, 2.29:1 (installer_contrast.py), below SC 1.4.3's 4.5:1. When the
# window opens, 1028 is hidden and 1256 takes Windows' own button text and
# face colours (SYSCLR 18 and 15), about 18:1, which also follow a
# high-contrast theme. Leaving the footer blank was tried and rejected:
# the empty controls stayed, named with a space, and Axe.Windows reported
# them ("The Name property must not contain only whitespace").
!macro axcessReadableFooter
  Push $0
  GetDlgItem $0 $HWNDPARENT 1028
  ShowWindow $0 0
  GetDlgItem $0 $HWNDPARENT 1256
  SetCtlColors $0 SYSCLR:18 SYSCLR:15
  Pop $0
!macroend

!ifndef BUILD_UNINSTALLER
  !define MUI_CUSTOMFUNCTION_GUIINIT axcessReadableFooter
  Function axcessReadableFooter
    !insertmacro axcessReadableFooter
  FunctionEnd
!else
  !define MUI_CUSTOMFUNCTION_UNGUIINIT un.axcessReadableFooter
  Function un.axcessReadableFooter
    !insertmacro axcessReadableFooter
  FunctionEnd
!endif

!macro customHeader
  # The version people see: 0.61, not the packaged 0.61.0 (see
  # displayVersion in src/updates.cjs).
  !searchparse /noerrors "${VERSION}" "" AXCESS_V_MAJOR "." AXCESS_V_MINOR "." AXCESS_V_PATCH
  !if "${AXCESS_V_PATCH}" != "0"
    !define AXCESS_DISPLAY_VERSION "${VERSION}"
  !else if ${AXCESS_V_MINOR} < 10
    !define AXCESS_DISPLAY_VERSION "${AXCESS_V_MAJOR}.0${AXCESS_V_MINOR}"
  !else
    !define AXCESS_DISPLAY_VERSION "${AXCESS_V_MAJOR}.${AXCESS_V_MINOR}"
  !endif

  !pragma warning push
  !pragma warning disable 6030

  # Every screen
  # The footer. axcessReadableFooter (below) draws it in readable colours.
  LangString ^Branding ${LANG_ENGLISH} "Axcess ${AXCESS_DISPLAY_VERSION}"
  LangString ^ClickNext ${LANG_ENGLISH} "Choose Next to continue."
  LangString ^ClickInstall ${LANG_ENGLISH} "When you are ready, choose Install."
  LangString ^ClickUninstall ${LANG_ENGLISH} "When you are ready, choose Uninstall."

  # Who to install for (electron-builder's assistedMessages.yml)
  LangString chooseInstallationOptions ${LANG_ENGLISH} "Choose who can use Axcess"
  LangString whoShouldThisApplicationBeInstalledFor ${LANG_ENGLISH} "Install it for you, or for everyone who uses this computer."
  LangString selectUserMode ${LANG_ENGLISH} "Only for me works without administrator permission. For everyone, Windows asks for it."
  LangString onlyForMe ${LANG_ENGLISH} "Only for &me"
  LangString forAll ${LANG_ENGLISH} "&Everyone who uses this computer"
  LangString freshInstallForCurrent ${LANG_ENGLISH} "Installs Axcess for your account only. You do not need administrator permission."
  LangString freshInstallForAll ${LANG_ENGLISH} "Installs Axcess for every account on this computer. Windows asks for administrator permission."
  # Shown as "<this> (<folder>)" and then reinstallUpgrade on the next line.
  LangString perUserInstallExists ${LANG_ENGLISH} "Axcess is already installed for your account "
  LangString perMachineInstallExists ${LANG_ENGLISH} "Axcess is already installed for everyone "
  LangString reinstallUpgrade ${LANG_ENGLISH} "Installing replaces it with this version. Axcess keeps your reports."
  LangString loginWithAdminAccount ${LANG_ENGLISH} "This needs an administrator account. Sign in with one, or choose Only for me."

  # Which copy to uninstall, shown only when Axcess is installed both ways.
  LangString chooseUninstallationOptions ${LANG_ENGLISH} "Choose which Axcess to uninstall"
  LangString whichInstallationShouldBeRemoved ${LANG_ENGLISH} "Axcess is installed for you and for everyone."
  LangString whichInstallationRemove ${LANG_ENGLISH} "Axcess is installed twice: for your account, and for everyone. Choose the one to uninstall."
  # Shown as "<this> (<folder>)" and then uninstall on the next line.
  LangString perUserInstall ${LANG_ENGLISH} "Installed for your account "
  LangString perMachineInstall ${LANG_ENGLISH} "Installed for everyone "
  LangString uninstall ${LANG_ENGLISH} "This copy will be uninstalled. Your reports stay on this computer."

  # Folder
  LangString MUI_TEXT_DIRECTORY_TITLE ${LANG_ENGLISH} "Choose a folder"
  LangString MUI_TEXT_DIRECTORY_SUBTITLE ${LANG_ENGLISH} "Choose where to install Axcess."
  LangString ^DirBrowseText ${LANG_ENGLISH} "Choose the folder to install Axcess in:"
  # The folder screen below (customPageAfterChangeDir).
  LangString axcessFolderIntro ${LANG_ENGLISH} "Setup installs Axcess in the folder below. To use a different folder, choose Browse. When you are ready, choose Install."
  LangString axcessFolderLabel ${LANG_ENGLISH} "Install &folder:"
  LangString axcessSpaceNeeded ${LANG_ENGLISH} "Space needed: about $1 MB"
  LangString axcessFolderEmpty ${LANG_ENGLISH} "Choose a folder to install Axcess in, then choose Install."

  # Installing
  LangString MUI_TEXT_INSTALLING_TITLE ${LANG_ENGLISH} "Installing Axcess"
  LangString MUI_TEXT_INSTALLING_SUBTITLE ${LANG_ENGLISH} "This can take a few minutes."
  LangString installing ${LANG_ENGLISH} "Installing Axcess. This can take a few minutes."
  LangString MUI_TEXT_FINISH_TITLE ${LANG_ENGLISH} "Axcess is installed"
  LangString MUI_TEXT_FINISH_SUBTITLE ${LANG_ENGLISH} "Choose Next to continue."
  LangString MUI_TEXT_ABORT_TITLE ${LANG_ENGLISH} "Axcess was not installed"
  LangString MUI_TEXT_ABORT_SUBTITLE ${LANG_ENGLISH} "Setup stopped before it finished. Run the installer again."

  # Last screen. $INSTDIR is filled in when the screen shows: the Squirrel
  # installer never said where Axcess went.
  LangString MUI_TEXT_FINISH_INFO_TITLE ${LANG_ENGLISH} "Axcess is installed"
  # Short: the "Open Axcess now" checkbox sits under this text, and it hid
  # a last line ("Choose Finish to close setup.") in the runner's
  # screenshot. A long folder path wraps to a second line.
  LangString MUI_TEXT_FINISH_INFO_TEXT ${LANG_ENGLISH} "Axcess is installed in this folder:$\r$\n$INSTDIR$\r$\n$\r$\nOpen it from the Start menu or from the shortcut on your desktop."
  LangString MUI_TEXT_FINISH_RUN ${LANG_ENGLISH} "&Open Axcess now"

  # Uninstall. Scans live in %APPDATA%\Axcess\data, outside the install
  # folder, and deleteAppDataOnUninstall is false, so they stay. Say so,
  # and say how to delete them: it is a privacy fact.
  LangString MUI_UNTEXT_WELCOME_INFO_TITLE ${LANG_ENGLISH} "Uninstall Axcess"
  LangString MUI_UNTEXT_WELCOME_INFO_TEXT ${LANG_ENGLISH} "This removes the Axcess app from this computer.$\r$\n$\r$\nYour reports stay in your user folder (%APPDATA%\Axcess\data). Axcess finds them again if you install it later. To delete them too, delete that folder after you uninstall.$\r$\n$\r$\nClose Axcess first, if it is open. $_CLICK"
  LangString MUI_UNTEXT_UNINSTALLING_TITLE ${LANG_ENGLISH} "Uninstalling Axcess"
  LangString MUI_UNTEXT_UNINSTALLING_SUBTITLE ${LANG_ENGLISH} "This can take a minute."
  LangString MUI_UNTEXT_FINISH_TITLE ${LANG_ENGLISH} "Axcess is uninstalled"
  LangString MUI_UNTEXT_FINISH_SUBTITLE ${LANG_ENGLISH} "Choose Next to continue."
  LangString MUI_UNTEXT_ABORT_TITLE ${LANG_ENGLISH} "Axcess was not uninstalled"
  LangString MUI_UNTEXT_ABORT_SUBTITLE ${LANG_ENGLISH} "Uninstall stopped. Try again from Windows Settings, in Apps."
  LangString MUI_UNTEXT_FINISH_INFO_TITLE ${LANG_ENGLISH} "Axcess is uninstalled"
  LangString MUI_UNTEXT_FINISH_INFO_TEXT ${LANG_ENGLISH} "The Axcess app is removed from this computer.$\r$\n$\r$\nYour reports are still in your user folder (%APPDATA%\Axcess\data).$\r$\n$\r$\nChoose Finish to close."
  LangString areYouSureToUninstall ${LANG_ENGLISH} "Uninstall Axcess from this computer? Your reports stay on this computer.$\r$\n$\r$\nChoose OK to uninstall, or Cancel to keep Axcess."

  # Messages (electron-builder's messages.yml)
  LangString win7Required ${LANG_ENGLISH} "Axcess needs Windows 10 or 11."
  LangString x64WinRequired ${LANG_ENGLISH} "Axcess needs 64-bit Windows."
  LangString appRunning ${LANG_ENGLISH} "Axcess is open. It needs to close first.$\r$\n$\r$\nChoose OK to close it now. A scan that is running stops.$\r$\nChoose Cancel to leave it open and stop."
  LangString appCannotBeClosed ${LANG_ENGLISH} "Axcess did not close.$\r$\n$\r$\nClose Axcess yourself, then choose Retry.$\r$\nChoose Cancel to stop."
  LangString appClosing ${LANG_ENGLISH} "Closing Axcess"
  # Setup adds a line with the error after this text.
  LangString decompressionFailed ${LANG_ENGLISH} "Setup could not unpack Axcess. The download may be damaged.$\r$\nDownload the installer again, then run it.$\r$\n$\r$\nDetails:"
  # Setup adds ": <error code>" after this text.
  LangString uninstallFailed ${LANG_ENGLISH} "Setup could not remove the old version of Axcess.$\r$\nClose Axcess, then run the installer again.$\r$\n$\r$\nError code"

  # Only if Windows needs a restart to replace a file that is in use.
  LangString MUI_TEXT_FINISH_INFO_REBOOT ${LANG_ENGLISH} "Restart your computer to finish installing Axcess. Restart now?"
  LangString MUI_UNTEXT_FINISH_INFO_REBOOT ${LANG_ENGLISH} "Restart your computer to finish uninstalling Axcess. Restart now?"
  LangString MUI_TEXT_FINISH_REBOOTNOW ${LANG_ENGLISH} "Restart now"
  LangString MUI_TEXT_FINISH_REBOOTLATER ${LANG_ENGLISH} "I will restart later"

  # Damaged download or a file in use. $0 is the file. Ignore leaves that
  # file out, so say what that risks.
  LangString ^ErrorDecompressing ${LANG_ENGLISH} "Setup could not unpack its files. The download may be damaged. Download the installer again."
  LangString ^InvalidOpcode ${LANG_ENGLISH} "The installer is damaged. Download it again."
  LangString ^FileError ${LANG_ENGLISH} "Setup could not write this file:$\r$\n$\r$\n$0$\r$\n$\r$\nIt may be in use. Close Axcess, then choose Retry.$\r$\nChoose Ignore to skip the file. Axcess may not work without it.$\r$\nChoose Abort to stop."
  LangString ^FileError_NoIgnore ${LANG_ENGLISH} "Setup could not write this file:$\r$\n$\r$\n$0$\r$\n$\r$\nIt may be in use. Close Axcess, then choose Retry.$\r$\nChoose Cancel to stop."

  # The log under "Show details": one line per step, then a file or folder.
  # Lines that name Windows internals ("Could not load: <plugin>") stay as
  # they are; they only help whoever reads a failed install's log.
  LangString ^Extract ${LANG_ENGLISH} "Unpack: "
  LangString ^ErrorWriting ${LANG_ENGLISH} "Could not write file: "
  LangString ^CantWrite ${LANG_ENGLISH} "Could not write: "
  LangString ^OutputFolder ${LANG_ENGLISH} "Folder: "
  LangString ^Exec ${LANG_ENGLISH} "Run: "
  LangString ^CopyDetails ${LANG_ENGLISH} "Copy details"

  !pragma warning pop
!macroend

# The folder screen. electron-builder's (NSIS's standard directory page)
# frames the folder field with a group box, and Windows does not take a
# group box as a field's name: Axe.Windows found the field with no name
# ("The Name property of a focusable element must not be null"), so a
# screen reader said "edit" and the path, not what it is for (SC 1.3.1
# Info and Relationships and SC 4.1.2 Name, Role, Value, Level A). That
# page has no hook for code, so electron-builder.config.cjs turns it off
# (allowToChangeInstallationDirectory: false) and this screen takes its
# place. A visible label sits right before the field, which is how Win32
# names a field (the label's text becomes the field's accessible name, as
# <label for> does on the web). Alt+F on the label moves to the field.
# The rest matches the old page: Browse, the space needed, the same
# header, and the same rule that Axcess gets a folder of its own.
!macro customPageAfterChangeDir
  !ifndef BUILD_UNINSTALLER
    !include nsDialogs.nsh
    !include StrContains.nsh
    Var axcessFolderField

    Page custom axcessFolderPageShow axcessFolderPageLeave

    Function axcessFolderPageShow
      # An update (electron-updater runs Setup with --updated) keeps the folder.
      ${if} ${isUpdated}
        Abort
      ${endif}
      !insertmacro MUI_HEADER_TEXT "$(MUI_TEXT_DIRECTORY_TITLE)" "$(MUI_TEXT_DIRECTORY_SUBTITLE)"
      nsDialogs::Create 1018
      Pop $0
      ${if} $0 == error
        Abort
      ${endif}
      ${NSD_CreateLabel} 0u 0u 300u 26u "$(axcessFolderIntro)"
      Pop $0
      # The label immediately before the field names it.
      ${NSD_CreateLabel} 0u 36u 300u 10u "$(axcessFolderLabel)"
      Pop $0
      ${NSD_CreateDirRequest} 0u 48u 238u 13u "$INSTDIR"
      Pop $axcessFolderField
      ${NSD_CreateBrowseButton} 244u 47u 56u 15u "$(^BrowseBtn)"
      Pop $0
      ${NSD_OnClick} $0 axcessFolderBrowse
      # Section 0 is electron-builder's install section; its size is in KB.
      SectionGetSize 0 $1
      IntOp $1 $1 / 1024
      ${NSD_CreateLabel} 0u 70u 300u 10u "$(axcessSpaceNeeded)"
      Pop $0
      ${NSD_SetFocus} $axcessFolderField
      nsDialogs::Show
    FunctionEnd

    Function axcessFolderBrowse
      ${NSD_GetText} $axcessFolderField $0
      nsDialogs::SelectFolderDialog "$(^DirBrowseText)" "$0"
      Pop $0
      ${if} $0 != error
        ${NSD_SetText} $axcessFolderField "$0"
      ${endif}
    FunctionEnd

    Function axcessFolderPageLeave
      ${NSD_GetText} $axcessFolderField $0
      ${if} $0 == ""
        MessageBox MB_OK|MB_ICONEXCLAMATION "$(axcessFolderEmpty)"
        Abort
      ${endif}
      StrCpy $INSTDIR $0
      # As electron-builder's own folder page does (instFilesPre).
      ${StrContains} $1 "${APP_FILENAME}" $INSTDIR
      ${if} $1 == ""
        StrCpy $INSTDIR "$INSTDIR\${APP_FILENAME}"
      ${endif}
    FunctionEnd
  !endif
!macroend

