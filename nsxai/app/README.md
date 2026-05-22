## Run Locally

**Prerequisites:** Node.js (frontend), Python 3.11+ (API + Fuseki via CLI)

### Full stack (recommended)

From the project root:

```bash
python nsxai_cli.py dev
```

Starts Fuseki, the FastAPI backend, and the Vite dev server.

### Frontend only

```bash
cd nsxai/app
npm install
npm run dev
```

The dev server runs on http://localhost:5173 and proxies `/api/*` to the Python API at http://localhost:8000. Start the API first:

```bash
python nsxai_cli.py start api
```

### Production build

```bash
npm run build
npm run preview
```

Set `VITE_API_BASE` when building if the API is not on the same origin (e.g. `VITE_API_BASE=http://localhost:8000 npm run build`).
