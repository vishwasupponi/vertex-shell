# Changelog

All notable changes to **Vertex Application** are documented in this file.

---

## [1.1.0] - 2026-11-28

### Added
- **Animated Splash Screen**: Displays an animated splash screen with live boot progress instead of launching silently in the background, and reports errors if startup fails.
- **1-Click App Self-Updater**: Allows updating Vertex directly from inside the app in a single click while preserving all installed modules and settings in `UserData/`.
- **Guided Windows Prerequisite Check**: Automatically detects missing Microsoft Edge WebView2 or `.NET` requirements on older Windows 10 systems and offers guided installation.

### Fixed
- **Windows 10 "Mark of the Web" Launch Block**: Fixed a Windows 10 issue where downloaded archives could be blocked from loading runtime components unless manually unblocked.
- **Embedded Hub Form Submissions**: Fixed JSON parsing errors when submitting interactive forms on the embedded Home dashboard.
- **Fresh Windows Runtime Compatibility**: Bundled additional Visual C++ runtime libraries so addon modules work on clean Windows 10/11 systems without extra installs.
- **Consistent App Versioning**: Synchronized the app version across the UI footer, settings, and update checker so version numbers always match.

Special thanks to **Rohith Rai** for spotting these issues and bringing them to my attention.

---

## [1.0.0] - 2026-11-24

- Initial public release of **Vertex Application**.
