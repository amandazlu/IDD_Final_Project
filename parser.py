def parse_file(file_path="charts/song01.json"):
    """Load a rhythm chart file and prepare event playback."""
    global chart_data

    if not os.path.exists(file_path):
        print(f"[ERROR] Chart file not found: {file_path}")
        return None

    try:
        with open(file_path, "r") as f:
            chart = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load chart: {e}")
        return None

    # Sort events by time (recommended for consistent playback)
    events = sorted(chart.get("events", []), key=lambda e: e["time"])
    chart_data = {
        "bpm": chart.get("bpm", 120),
        "offset": chart.get("offset", 0.0),
        "events": events,
    }

    print(f"[CHART LOADED] {len(events)} events loaded")
    return chart_data

parse_file()