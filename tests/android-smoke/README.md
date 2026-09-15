# Android API 35 smoke checklist

Run only against an isolated server database and fake aTimeLogger service.

- [ ] A request with `Origin: https://localhost` passes `/auth/login` and `/api/sync/pull` CORS preflight without mutating the standard server config.
- [ ] A future running countdown has exactly one pending local notification; pause/end cancels it and force-stop recovery recreates it.
- [ ] Every `/icons/atm/*.png` request succeeds from packaged WebView assets and the ATM 404 count is zero.
- [ ] Logcat contains zero `duplicate column` messages during first install and restart.
- [ ] Saved username appears after restart without exposing password/token; SQLite, Outbox and Preferences sensitive-value counts are zero.

Also require zero FATAL, cleartext-policy and SSL errors, a progressing sync cursor, and exact cleanup of the test AVD, reverse mappings and isolated service PIDs.

## Sleep image upload

Install the current Debug APK, log in only to the test environment, open Sleep, choose a normal image, wait for “截图日期校验通过” or completed analysis, then choose the same image again. Validate the corresponding server log without exposing credentials:

```powershell
.\tests\android-smoke\verify_sleep_upload.ps1 -ServerLog .\server_log.txt -Serial emulator-5554
```

Repeat with an image close to 15 MB. Success requires no `Failed to fetch`, a server `Upload received` request ID, and matching `uploaded/done` evidence. The script never reads or prints the auth token or image body.
