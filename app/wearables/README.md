## Health Integration Gateway

Frontend and mobile clients should only call the backend gateway endpoints under `/integrations`.

### OAuth providers
- `Fitbit`: browser OAuth connect, backend callback, backend token storage, queued sync.
- `Google Fit`: browser Google OAuth connect, backend callback, backend token storage, queued sync.
- `Garmin`: browser/provider flow only when Garmin partner credentials are configured. If not configured, the API returns `provider_not_configured`.

### Native mobile providers
- `Apple Watch / Apple Health`: native iOS HealthKit permission flow in the mobile app, then `POST /integrations/native/connected` and `POST /integrations/native/samples`.
- `Health Connect`: native Android permission flow in the mobile app, then `POST /integrations/native/connected` and `POST /integrations/native/samples`.
- `This Phone`: frontend maps this to Apple Watch / Apple Health on iOS or Health Connect on Android.

### Import providers
- `QR / Other Device`: use `POST /integrations/import/qr` or `POST /integrations/import/file`.

### Queue behavior
- Manual provider sync requests enqueue a sync job and return immediately.
- The in-process queue worker handles provider sync execution and import processing.
- Sync job state is persisted in `sync_jobs`, and failures are recorded in `sync_errors`.

### Provider status values
- `connected`
- `disconnected`
- `needs_permission`
- `syncing`
- `error`
- `provider_not_configured`
