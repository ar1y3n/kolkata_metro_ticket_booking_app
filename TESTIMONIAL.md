# TESTIMONIAL

## Approach

I started by cloning the repository and reading through the full backend and
frontend structure before touching any code, so I understood how the pieces
were meant to fit together: FastAPI serving a REST API, PostgreSQL holding
dynamic data (tickets, system config), and a read-only SQLite database
holding the static Kolkata Metro station/line graph.

Rather than jumping straight to Feature 3 (the shortest-route logic), I first
got the app running end-to-end so I could see real errors instead of guessing.
That surfaced a handful of environment and configuration bugs that were
blocking every other feature, so I fixed those first, then moved on to the
two genuinely missing pieces of logic.

## Bugs found and fixed

1. **SQLite path resolution (`sqlite_client.py`)** — `DB_PATH` was built by
   appending a filename directly onto the *module file's* path instead of its
   parent directory, and the filename itself had a typo (missing underscore).
   Fixed by using `Path(__file__).resolve().parent / "metadata_graph.db"`.

2. **CORS origin mismatch (`main.py`)** — the backend only allowed
   `http://localhost:3000`, but Vite serves on `5173` by default. Every
   frontend API call was being blocked before it reached the server. Updated
   the allowed origin to match.

3. **Missing backend dependency (`requirements.txt`)** — `sqlalchemy` is
   imported directly in three files (`postgres_client.py`, `routes.py`,
   `unlock_service.py`) but was never listed as a dependency. Added it.

4. **Broken DB connection string (`.env.example`)** — `localhost5432` was
   missing the colon before the port. Fixed to `localhost:5432`.

5. **Missing frontend dependency (`package.json`)** — `lucide-react` is used
   for icons across every component but wasn't declared. Added it.

6. **Frontend/backend port mismatch (`api.js`)** — the API client defaulted
   to `http://localhost:8080/api`, but the backend runs on `8000`. Resolved
   with a `VITE_API_URL` environment variable pointing at the correct port.

7. **`/allstations` endpoint unimplemented (`routes.py`)** — despite the
   assignment notes describing this as already done, the handler was just
   `pass`, which FastAPI rejected with a `ResponseValidationError` since the
   response model expects a list. Implemented it to query the `stations`
   table from SQLite and return the results.

8. **Shortest-route logic unimplemented (`graph_engine.py`)** — this was the
   core task: `get_metro_route` was empty. I implemented Dijkstra's algorithm
   over a graph built from the `connections` table (train travel, weighted by
   minutes) and the `interchanges` table (line transfers, weighted by
   transfer time). One detail that needed care: several stations (e.g.
   Esplanade, Park Street) exist as separate line-specific rows in the
   `stations` table, so a route search by station *name* has to consider
   every line-variant of both the source and destination as valid start/end
   points. I handled this with a multi-source, multi-target Dijkstra that
   starts from all matching source nodes at once and stops at the first
   matching destination node popped off the priority queue — which is
   guaranteed to be the globally shortest option since all edge weights are
   non-negative. The function returns the exact `route_summary` /
   `ordered_itinerary` shape the existing frontend already expected, so no
   frontend or API contract changes were needed.

## Challenges

The trickiest part wasn't the algorithm itself — it was recognizing that
interchange stations aren't single graph nodes; treating "Esplanade" as one
node instead of three (one per line) would have produced wrong or impossible
routes. Reading the schema doc (`sqlite_ddl_description.md`) carefully before
writing any query logic saved time here.

The other challenge was diagnosing environment-vs-code issues quickly —
several early symptoms (all diagnostic checks failing) looked like a single
big problem but turned out to be two independent issues (a local Postgres
password mismatch, and the frontend pointing at the wrong backend port)
that happened to surface together.

## Learnings

- Silent `except` blocks that only `print()` errors are convenient during
  development but make debugging from the UI alone impossible — the real
  fix info was always in the backend terminal, not the frontend.
- Verifying each fix in isolation (testing the SQLite query directly, then
  the endpoint via FastAPI's TestClient, then the full route through the
  browser) made it much easier to pinpoint exactly which layer a problem was
  in, rather than only testing through the UI at the end.
- Multi-source/multi-target shortest-path problems come up more often than
  they first appear — treating "a station" as potentially several graph
  nodes was a useful reminder to model the data as it actually is, not as it
  first looks from the UI.
