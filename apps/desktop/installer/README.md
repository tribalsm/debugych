# NSIS template provenance

`installer.nsi` is the official Tauri CLI 2.12.4 template:
https://github.com/tauri-apps/tauri/blob/tauri-cli-v2.12.4/crates/tauri-bundler/src/bundle/windows/nsis/installer.nsi

Only the two `CheckIfAppIsRunning` invocations are replaced with `DebugychRequireClosed` from hooks.nsh. The replacement uses Windows Restart Manager to check the exact installation executable and aborts with a message if it is running. It never calls RmShutdown, taskkill or process termination. Silent install/uninstall also aborts on a running app.

Stock per-user installation, resources, shortcuts, registered uninstall, WebView2 handling and reinstall pages remain unchanged. Review this minimal patch when updating Tauri CLI. Template is licensed under the upstream MIT/Apache-2.0 terms; see https://github.com/tauri-apps/tauri for notices.
