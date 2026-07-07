# V2 Hourly Automation Dashboard

This is a sanitized GitHub Pages package for the V2 hourly automation timetable.

It intentionally includes only:

- `index.html`
- `data/dashboard_state.json`
- `reports/*.html`

No account holdings, factor logs, raw market data, or private run artifacts are included.

The hourly automation syncs the sanitized timetable and public summary pages
into this package after each slot run. Updating the live GitHub Pages site still
requires this package to be committed and pushed to the Pages repository, or a
CI job that performs that publish step.

## Local Preview

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8765/index.html
```

## GitHub Pages

Enable Pages from the repository's `main` branch and root directory.
