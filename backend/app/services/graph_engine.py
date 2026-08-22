import heapq
from app.db.sqlite_client import get_sqlite_conn


def _load_graph(conn):
    """
    Loads stations, connections, and interchanges from SQLite and builds an
    adjacency list keyed by station id.

    Each edge is a dict:
        {
            "to": <station_id>,
            "weight": <minutes>,
            "type": "train" | "transfer",
            "fare": <int, 0 for transfers>,
        }
    """
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, line FROM stations;")
    stations = {row["id"]: {"name": row["name"], "line": row["line"]} for row in cursor.fetchall()}

    adjacency = {station_id: [] for station_id in stations}

    cursor.execute("SELECT station_a_id, station_b_id, travel_time_minutes, fare_inr FROM connections;")
    for row in cursor.fetchall():
        if row["station_a_id"] in adjacency:
            adjacency[row["station_a_id"]].append({
                "to": row["station_b_id"],
                "weight": row["travel_time_minutes"],
                "type": "train",
                "fare": row["fare_inr"],
            })

    cursor.execute("SELECT station_from_id, station_to_id, transfer_time_minutes FROM interchanges;")
    for row in cursor.fetchall():
        if row["station_from_id"] in adjacency:
            adjacency[row["station_from_id"]].append({
                "to": row["station_to_id"],
                "weight": row["transfer_time_minutes"],
                "type": "transfer",
                "fare": 0,
            })

    return stations, adjacency


def _dijkstra(adjacency, source_ids, target_ids):
    """
    Multi-source, multi-target Dijkstra over the station graph.

    Returns (destination_id, distances, predecessors) for the first target
    node popped off the priority queue - by Dijkstra's guarantee this is the
    globally shortest-time path among all source/destination node pairs
    (since all edge weights are non-negative).
    """
    distances = {station_id: float("inf") for station_id in adjacency}
    predecessors = {}  # station_id -> (prev_station_id, edge_type, fare)
    visited = set()

    heap = []
    for src_id in source_ids:
        distances[src_id] = 0
        heapq.heappush(heap, (0, src_id))

    target_set = set(target_ids)

    while heap:
        current_dist, current_id = heapq.heappop(heap)

        if current_id in visited:
            continue
        visited.add(current_id)

        if current_id in target_set:
            return current_id, distances, predecessors

        for edge in adjacency.get(current_id, []):
            neighbor = edge["to"]
            if neighbor in visited:
                continue
            new_dist = current_dist + edge["weight"]
            if new_dist < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_dist
                predecessors[neighbor] = (current_id, edge["type"], edge["fare"])
                heapq.heappush(heap, (new_dist, neighbor))

    return None, distances, predecessors


def _reconstruct_path(destination_id, predecessors):
    """
    Walks the predecessor chain from destination back to whichever source
    node the search started from, returning an ordered list of
    (station_id, incoming_edge_type, fare) tuples from source to destination.
    The source node's incoming edge type is None.
    """
    path = []
    node = destination_id
    while node in predecessors:
        prev_id, edge_type, fare = predecessors[node]
        path.append((node, edge_type, fare))
        node = prev_id
    path.append((node, None, 0))  # the source node itself
    path.reverse()
    return path


def get_metro_route(source_name: str, destination_name: str):
    """
    Computes the shortest route (based on travel time) between the source and
    destination metro stations using Dijkstra's algorithm.
    Reads station, connection, and interchange graphs dynamically from SQLite.
    """
    if not source_name or not destination_name:
        raise ValueError("Both source and destination station names are required.")

    if source_name.strip().lower() == destination_name.strip().lower():
        raise ValueError("Source and destination stations cannot be the same.")

    with get_sqlite_conn() as conn:
        stations, adjacency = _load_graph(conn)

    # A station name can map to several nodes (one per line, for interchange
    # stations), so resolve every matching id for source and destination.
    source_ids = [sid for sid, info in stations.items() if info["name"].lower() == source_name.strip().lower()]
    destination_ids = [sid for sid, info in stations.items() if info["name"].lower() == destination_name.strip().lower()]

    if not source_ids:
        raise ValueError(f"Unknown source station: '{source_name}'.")
    if not destination_ids:
        raise ValueError(f"Unknown destination station: '{destination_name}'.")

    reached_id, distances, predecessors = _dijkstra(adjacency, source_ids, destination_ids)

    if reached_id is None:
        raise ValueError(f"No route found between '{source_name}' and '{destination_name}'.")

    path = _reconstruct_path(reached_id, predecessors)

    ordered_itinerary = []
    total_fare = 0
    total_time = distances[reached_id]
    interchange_count = 0

    for idx, (station_id, incoming_edge_type, fare) in enumerate(path):
        info = stations[station_id]
        is_interchange = False
        transfer_to_line = None

        # Mark the node as an interchange point if the NEXT hop out of it is
        # a transfer edge - i.e. this is where the passenger switches lines.
        if idx + 1 < len(path):
            next_station_id, next_edge_type, _ = path[idx + 1]
            if next_edge_type == "transfer":
                is_interchange = True
                transfer_to_line = stations[next_station_id]["line"]
                interchange_count += 1

        if incoming_edge_type == "train":
            total_fare += fare

        ordered_itinerary.append({
            "station_name": info["name"],
            "line": info["line"],
            "is_interchange": is_interchange,
            "transfer_to": transfer_to_line,
        })

    route_summary = {
        "source": source_name,
        "destination": destination_name,
        "total_fare_inr": total_fare,
        "total_travel_time_minutes": total_time,
        "interchanges_count": interchange_count,
    }

    return {
        "route_summary": route_summary,
        "ordered_itinerary": ordered_itinerary,
    }
