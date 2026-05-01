from __future__ import annotations

from datetime import datetime
import math
import random

import pandas as pd
import pydeck as pdk
import streamlit as st


# Wide layout keeps the app easy to scan like a lightweight ops dashboard.
st.set_page_config(page_title="RidePulse", page_icon="📍", layout="wide")


TIME_FACTORS = {
    "Morning": 0.95,
    "Afternoon": 1.00,
    "Evening": 1.18,
    "Night": 1.08,
}

LEVEL_COLORS = {
    "LOW": [34, 197, 94, 210],
    "MEDIUM": [249, 115, 22, 220],
    "HIGH": [239, 68, 68, 230],
    "USER": [96, 165, 250, 235],
}

BAY_AREA_BOUNDS = {
    "north": 38.85,
    "south": 36.95,
    "west": -123.20,
    "east": -121.45,
}

BAY_AREA_PLACES = [
    {"name": "San Francisco", "lat": 37.7749, "lon": -122.4194},
    {"name": "Mission District", "lat": 37.7599, "lon": -122.4148},
    {"name": "SoMa", "lat": 37.7786, "lon": -122.4059},
    {"name": "Sunset District", "lat": 37.7534, "lon": -122.4944},
    {"name": "Richmond District", "lat": 37.7802, "lon": -122.4827},
    {"name": "SFO Airport", "lat": 37.6213, "lon": -122.3790},
    {"name": "Oakland", "lat": 37.8044, "lon": -122.2712},
    {"name": "Berkeley", "lat": 37.8715, "lon": -122.2730},
    {"name": "Emeryville", "lat": 37.8395, "lon": -122.2892},
    {"name": "Walnut Creek", "lat": 37.9101, "lon": -122.0652},
    {"name": "Concord", "lat": 37.9780, "lon": -122.0311},
    {"name": "San Rafael", "lat": 37.9735, "lon": -122.5311},
    {"name": "Santa Rosa", "lat": 38.4405, "lon": -122.7144},
    {"name": "Napa", "lat": 38.2975, "lon": -122.2869},
    {"name": "Redwood City", "lat": 37.4852, "lon": -122.2364},
    {"name": "Palo Alto", "lat": 37.4419, "lon": -122.1430},
    {"name": "Mountain View", "lat": 37.3861, "lon": -122.0839},
    {"name": "Sunnyvale", "lat": 37.3688, "lon": -122.0363},
    {"name": "Santa Clara", "lat": 37.3541, "lon": -121.9552},
    {"name": "San Jose", "lat": 37.3382, "lon": -121.8863},
    {"name": "Fremont", "lat": 37.5483, "lon": -121.9886},
]


def clamp(value: float, low: float, high: float) -> float:
    """Keep values inside a clean range for UI display."""
    return max(low, min(high, value))


def demand_level(score: float) -> str:
    """Convert a numeric demand score into an easy label."""
    if score >= 72:
        return "HIGH"
    if score >= 48:
        return "MEDIUM"
    return "LOW"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute distance between two lat/lon points in kilometers."""
    radius_km = 6371.0
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def is_within_bay_area(lat: float, lon: float) -> bool:
    """Keep the experience focused on the Bay Area only."""
    return (
        BAY_AREA_BOUNDS["south"] <= lat <= BAY_AREA_BOUNDS["north"]
        and BAY_AREA_BOUNDS["west"] <= lon <= BAY_AREA_BOUNDS["east"]
    )


def place_lookup(place_name: str) -> dict:
    """Return coordinates for one supported Bay Area place."""
    for place in BAY_AREA_PLACES:
        if place["name"] == place_name:
            return place
    return BAY_AREA_PLACES[0]


def generate_zones(center_lat: float, center_lon: float, center_label: str) -> list[dict]:
    """Choose the nearest real Bay Area places instead of synthetic directions."""
    center_seed = int(abs(center_lat * 1000) + abs(center_lon * 1000))
    zones = []

    candidates = []
    for place in BAY_AREA_PLACES:
        if place["name"] == center_label:
            continue
        distance_km = haversine_km(center_lat, center_lon, place["lat"], place["lon"])
        candidates.append({**place, "distance_km": distance_km})

    nearest_places = sorted(candidates, key=lambda item: item["distance_km"])[:6]
    for place in nearest_places:
        zone_rng = random.Random(f"{center_seed}-{place['name']}")
        base_demand = 42 + zone_rng.randint(0, 20)
        zones.append(
            {
                "zone": place["name"],
                "zone_direction": place["name"],
                "lat": place["lat"],
                "lon": place["lon"],
                "base_demand": base_demand,
            }
        )
    return zones


def short_place_label(full_label: str) -> str:
    """Create a short stable base name from the geocoded user location."""
    if not full_label.strip():
        return "Focus Area"
    parts = [part.strip() for part in full_label.split(",") if part.strip()]
    return parts[0] if parts else "Focus Area"


def calculate_current_demand(
    base_demand: float,
    zone_name: str,
    zone_direction: str,
    center_lat: float,
    center_lon: float,
    time_of_day: str,
    event_boost: int,
    event_happening: bool,
    rainy_weather: bool,
) -> float:
    """Simulate current demand from time, weather, and event conditions."""
    score = base_demand * TIME_FACTORS[time_of_day]
    location_rng = random.Random(f"{round(center_lat, 3)}-{round(center_lon, 3)}-{zone_direction}")

    # Evening and night naturally push marketplace activity up.
    if time_of_day == "Evening":
        score += 10
    elif time_of_day == "Night":
        score += 5

    # Events concentrate demand near a couple of nearby zones.
    score += event_boost

    # Rain increases both ride and delivery demand city-wide.
    if rainy_weather:
        score += 12

    # Different areas behave differently based on local context.
    score += location_rng.randint(-8, 8)

    # Small deterministic differences keep zones from feeling too uniform.
    zone_rng = random.Random(f"{zone_name}-{time_of_day}-{event_happening}-{rainy_weather}")
    score += zone_rng.randint(-4, 4)
    return clamp(score, 18, 100)


def explanation_text(row: pd.Series, event_happening: bool, rainy_weather: bool) -> str:
    """Explain why a zone is recommended or not."""
    reasons = []
    if row["future_demand"] >= 70:
        reasons.append("future demand stays strong")
    if row["travel_time_min"] <= 10:
        reasons.append("travel time is short")
    if row["travel_time_min"] >= 16:
        reasons.append("travel time is long")
    if event_happening and row["event_boost"] >= 12:
        reasons.append("event activity is pulling demand nearby")
    if rainy_weather:
        reasons.append("rain is lifting requests")

    if not reasons:
        return "Balanced demand and travel time."
    return ", ".join(reasons).capitalize() + "."


def build_zone_frame(
    center_lat: float,
    center_lon: float,
    center_label: str,
    time_of_day: str,
    event_happening: bool,
    rainy_weather: bool,
) -> pd.DataFrame:
    """Build all nearby zone metrics for the decision engine."""
    rows = []

    for zone in generate_zones(center_lat, center_lon, center_label):
        event_rng = random.Random(f"event-{round(center_lat, 3)}-{round(center_lon, 3)}-{zone['zone_direction']}")
        event_boost = (5 + event_rng.randint(0, 12)) if event_happening else 0
        current_demand = calculate_current_demand(
            zone["base_demand"],
            zone["zone"],
            zone["zone_direction"],
            center_lat,
            center_lon,
            time_of_day,
            event_boost,
            event_happening,
            rainy_weather,
        )
        distance_km = haversine_km(center_lat, center_lon, zone["lat"], zone["lon"])
        travel_time_min = distance_km * 2

        # Future demand decays as the driver spends time getting there.
        future_demand = clamp(current_demand - (travel_time_min / 30), 10, 100)

        # Score favors zones where future opportunity remains high after travel.
        score = future_demand - (travel_time_min * 0.65)
        level = demand_level(current_demand)
        future_level = demand_level(future_demand)

        rows.append(
            {
                **zone,
                "distance_km": round(distance_km, 1),
                "travel_time_min": round(travel_time_min, 1),
                "current_demand": round(current_demand, 1),
                "current_level": level,
                "future_demand": round(future_demand, 1),
                "future_level": future_level,
                "score": round(score, 1),
                "event_boost": event_boost,
                "color": LEVEL_COLORS[future_level],
                "radius": 220 + future_demand * 10,
            }
        )

    df = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    df["explanation"] = df.apply(explanation_text, axis=1, event_happening=event_happening, rainy_weather=rainy_weather)
    return df


def build_user_marker(center_lat: float, center_lon: float, label: str) -> pd.DataFrame:
    """Create a single marker for the user location on the map."""
    return pd.DataFrame(
        [
            {
                "zone": label,
                "lat": center_lat,
                "lon": center_lon,
                "color": LEVEL_COLORS["USER"],
                "radius": 260,
            }
        ]
    )


st.markdown(
    """
    <style>
    .stApp {
        background: #f4f7fb;
        color: #0f172a;
    }
    [data-testid="stHeader"] {
        background: rgba(0, 0, 0, 0);
    }
    [data-testid="stSidebar"] {
        background: #ffffff;
    }
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #dbe4ee;
        border-radius: 14px;
        padding: 0.8rem 0.9rem;
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
    }
    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    label,
    .stTextInput label,
    .stSelectbox label,
    .stCheckbox label {
        color: #0f172a !important;
    }
    h1, h2, h3, h4, h5, h6,
    p,
    small,
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] strong {
        color: #0f172a !important;
    }
    .stCheckbox label p,
    .stSelectbox label p,
    .stTextInput label p,
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] input,
    div[data-baseweb="select"] div,
    div[data-baseweb="select"] *:not(svg),
    input::placeholder {
        color: #0f172a !important;
        opacity: 1 !important;
    }
    .stTextInput input,
    .stSelectbox div[data-baseweb="select"] > div {
        background: #ffffff !important;
        border-color: #cbd5e1 !important;
    }
    .stDataFrame, .stTable {
        background: #ffffff;
        border-radius: 14px;
    }
    .hero {
        padding: 0.4rem 0 1rem 0;
    }
    .hero h1 {
        margin: 0;
        color: #0f172a;
        letter-spacing: -0.03em;
    }
    .hero p {
        margin: 0.35rem 0 0;
        color: #475569;
        max-width: 760px;
    }
    .panel {
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
    }
    .section-label {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #0369a1;
        margin-bottom: 0.75rem;
        font-weight: 700;
    }
    .decision-item {
        padding: 0.8rem 0.9rem;
        margin-bottom: 0.65rem;
        background: #f8fafc;
        border: 1px solid rgba(148, 163, 184, 0.15);
        border-radius: 14px;
        color: #0f172a;
    }
    .detail-row {
        padding: 0.45rem 0;
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    }
    .detail-row:last-child {
        border-bottom: none;
    }
    .footnote {
        color: #64748b;
        font-size: 0.92rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    """
    <div class="hero">
        <h1>RidePulse</h1>
        <p>We built a decision-making system that helps drivers and operations teams identify where to go, when to act, and which areas to avoid based on real-time demand signals.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<p style="color:#475569; margin-top:-0.4rem;">Choose one of the supported Bay Area places below. The selector supports typeahead/autocomplete within this list. Focus areas are now the nearest real Bay Area places around your selected location.</p>',
    unsafe_allow_html=True,
)


# Simple top controls keep the UI easy while making the system flexible.
control_cols = st.columns([1.8, 1, 0.9, 0.9], gap="medium")
with control_cols[0]:
    selected_place_name = st.selectbox(
        "Choose a Bay Area place",
        options=[place["name"] for place in BAY_AREA_PLACES],
        index=19,
        placeholder="Select a Bay Area place",
    )
with control_cols[1]:
    time_of_day = st.selectbox("Time of day", ["Morning", "Afternoon", "Evening", "Night"], index=2)
with control_cols[2]:
    event_happening = st.checkbox("Event", value=False)
with control_cols[3]:
    rainy_weather = st.checkbox("Rainy weather", value=False)

location_data = place_lookup(selected_place_name)


zone_df = build_zone_frame(
    center_lat=location_data["lat"],
    center_lon=location_data["lon"],
    center_label=location_data["name"],
    time_of_day=time_of_day,
    event_happening=event_happening,
    rainy_weather=rainy_weather,
)

best_zone = zone_df.iloc[0]
avoid_zones = zone_df.sort_values("score", ascending=True).head(2)
focused_zone_name = st.selectbox("Focus area", zone_df["zone"].tolist(), index=0)
focused_zone = zone_df.loc[zone_df["zone"] == focused_zone_name].iloc[0]
last_updated = datetime.now().strftime("%I:%M:%S %p")


summary_top = st.columns(3, gap="medium")
summary_top[0].metric("📊 Demand", best_zone["future_level"])
summary_top[1].metric("🏆 Best Area", best_zone["zone"])
summary_top[2].metric("🚫 Avoid Area", avoid_zones.iloc[0]["zone"])

summary_bottom = st.columns(2, gap="medium")
summary_bottom[0].metric("⏱️ Travel Time", f"{best_zone['travel_time_min']} min")
summary_bottom[1].metric("📍 Distance", f"{best_zone['distance_km']} km")


main_cols = st.columns([1.65, 1], gap="large")

with main_cols[0]:
    with st.container():
        st.subheader("📍 Map")

        user_marker = build_user_marker(location_data["lat"], location_data["lon"], "You")

        zone_layer = pdk.Layer(
            "ScatterplotLayer",
            data=zone_df,
            get_position="[lon, lat]",
            get_fill_color="color",
            get_radius="radius",
            pickable=True,
            opacity=0.84,
            stroked=True,
            get_line_color=[15, 23, 42, 180],
            line_width_min_pixels=1.5,
        )
        user_layer = pdk.Layer(
            "ScatterplotLayer",
            data=user_marker,
            get_position="[lon, lat]",
            get_fill_color="color",
            get_radius="radius",
            pickable=False,
            opacity=0.95,
            stroked=True,
            get_line_color=[255, 255, 255, 220],
            line_width_min_pixels=2,
        )
        label_layer = pdk.Layer(
            "TextLayer",
            data=zone_df,
            get_position="[lon, lat]",
            get_text="zone",
            get_color=[15, 23, 42, 220],
            get_size=14,
            get_alignment_baseline="'top'",
            get_pixel_offset=[0, 16],
        )

        st.pydeck_chart(
            pdk.Deck(
                layers=[zone_layer, user_layer, label_layer],
                initial_view_state=pdk.ViewState(
                    latitude=location_data["lat"],
                    longitude=location_data["lon"],
                    zoom=11,
                    pitch=32,
                ),
                map_provider="carto",
                map_style=pdk.map_styles.LIGHT,
                tooltip={
                    "html": """
                        <b>{zone}</b><br/>
                        Future demand: {future_level}<br/>
                        Score: {score}<br/>
                        Distance: {distance_km} km<br/>
                        Travel time: {travel_time_min} min
                    """,
                    "style": {"backgroundColor": "#0f172a", "color": "#ffffff"},
                },
            ),
            use_container_width=True,
        )
        st.markdown(
            '<div class="footnote">Blue marker = your location. Green/orange/red zones reflect future demand after travel time is considered.</div>',
            unsafe_allow_html=True,
        )

with main_cols[1]:
    with st.container():
        st.subheader("Decision Output")
        st.caption("Use `Focus area` to drill into any nearby zone and learn more about that specific area.")
        st.markdown(f'<div class="decision-item">🏆 Best zone to go: <strong>{best_zone["zone"]}</strong></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="decision-item">🚫 Zones to avoid: <strong>{", ".join(avoid_zones["zone"].tolist())}</strong></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="decision-item">💡 Recommended action: Move toward <strong>{best_zone["zone"]}</strong> now. '
            f'Its future demand stays at <strong>{best_zone["future_level"]}</strong> even after the estimated {best_zone["travel_time_min"]} minute trip.</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="decision-item">⏱️ Timing insight: The strongest opportunity should hold for roughly the next trip window, '
            f'so repositioning early is better than waiting if you are targeting <strong>{best_zone["zone"]}</strong>.</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="decision-item">📍 Distance and travel time: {best_zone["distance_km"]} km away, about {best_zone["travel_time_min"]} minutes.</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="decision-item">📊 Future demand level: <strong>{best_zone["future_level"]}</strong> '
            f'with score <strong>{best_zone["score"]}</strong>.</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height: 1rem;"></div>', unsafe_allow_html=True)
    with st.container():
        st.subheader("Focus Area Details")
        st.markdown(
            f"""
            <div class="detail-row"><strong>{focused_zone["zone"]}</strong></div>
            <div class="detail-row">Current demand: <strong>{focused_zone["current_demand"]}</strong> ({focused_zone["current_level"]})</div>
            <div class="detail-row">Future demand: <strong>{focused_zone["future_demand"]}</strong> ({focused_zone["future_level"]})</div>
            <div class="detail-row">Distance: <strong>{focused_zone["distance_km"]} km</strong></div>
            <div class="detail-row">Travel time: <strong>{focused_zone["travel_time_min"]} min</strong></div>
            <div class="detail-row">Decision score: <strong>{focused_zone["score"]}</strong></div>
            <div class="detail-row">Explanation: <strong>{focused_zone["explanation"]}</strong></div>
            """,
            unsafe_allow_html=True,
        )


st.markdown('<div style="height: 1rem;"></div>', unsafe_allow_html=True)
with st.container():
    st.subheader("Zone Ranking")
    st.dataframe(
        zone_df[["zone", "distance_km", "travel_time_min", "current_demand", "future_demand", "future_level", "score"]],
        use_container_width=True,
        hide_index=True,
    )
    st.markdown(f'<div class="footnote">Last updated: {last_updated} · Selected place: {location_data["name"]}</div>', unsafe_allow_html=True)
