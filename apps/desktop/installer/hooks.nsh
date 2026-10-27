; Tauri 2.12.4 installer extension: never force-stop an application.
!macro DebugychRequireClosed
  !insertmacro RestartManager_StartSession $R0
  ${If} $R0 != ""
    !insertmacro RestartManager_RegisterFile $R0 "$INSTDIR\${MAINBINARYNAME}.exe"
    ${If} $0 = 0
      System::Call 'RSTRTMGR::RmGetList(p R0, *i .r1, *i .r2, p 0, *i .r3) i .r0'
      ${If} $0 = ${ERROR_MORE_DATA}
        !insertmacro RestartManager_EndSession $R0
        IfSilent +2 0
        MessageBox MB_OK|MB_ICONEXCLAMATION "Close Debugych from its Exit menu before installing or removing this version. No process has been terminated."
        Abort
      ${EndIf}
    ${EndIf}
    !insertmacro RestartManager_EndSession $R0
  ${EndIf}
!macroend
