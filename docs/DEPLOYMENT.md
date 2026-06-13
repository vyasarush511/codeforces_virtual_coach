# Public Deployment

The project needs a backend because the dashboard fetches live Codeforces data, caches responses, and computes recommendations. GitHub Pages alone is not enough for the full version because it only hosts static files.

Use Render for the public demo link.

## Render Deployment

1. Create a new GitHub repository.
2. Put the contents of `codeforces-virtual-coach` at the repository root.
3. Push to GitHub.
4. Open Render and create a new Web Service from the GitHub repo.
5. Render will detect `render.yaml`.
6. Deploy.
7. Copy the generated `https://...onrender.com` URL.
8. Paste that URL into the top of `README.md` as the live demo link.

## Build Settings

These are already encoded in `render.yaml`.

```text
Runtime: Python
Build Command: pip install -r requirements.txt
Start Command: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /api/health
```

## Notes

- Render's free instance may sleep after inactivity, so the first request can be slow.
- `CF_COACH_CACHE_PATH=/tmp/cf_cache.sqlite3` is used on Render because the filesystem is ephemeral.
- The app works without secrets because it only uses public Codeforces API endpoints.

