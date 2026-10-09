# Inside the Game — UI

React + TypeScript (Vite). Shows verified match recaps where every sentence links to its evidence:
the events on a pitch and in a table, the stat totals, or similar moments from other matches.

```bash
npm install
npm run dev        # http://localhost:5173 — proxies /api to the backend on port 8000
npm run build      # production build in dist/; set VITE_API_URL to the backend URL
```

Run the backend first from the repo root: `uvicorn inside_the_game.api:app --port 8000`.
