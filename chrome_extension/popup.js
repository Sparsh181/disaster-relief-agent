const API = "http://localhost:8000";
let userLat = null, userLon = null;

async function init() {
  // Get user location
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(pos => {
      userLat = pos.coords.latitude;
      userLon = pos.coords.longitude;
      document.getElementById("location-bar").textContent =
        `📍 ${userLat.toFixed(2)}, ${userLon.toFixed(2)} (your location)`;
      loadAlerts();
    }, () => {
      document.getElementById("location-bar").textContent = "📍 Location unavailable — showing all alerts";
      loadAlerts();
    });
  } else {
    loadAlerts();
  }
}

async function loadAlerts() {
  const container = document.getElementById("alerts-container");
  try {
    let url = userLat
      ? `${API}/alerts/nearby?lat=${userLat}&lon=${userLon}&radius_km=5000&min_severity=Green`
      : `${API}/alerts/live?min_severity=Green&max_results=10`;

    const res  = await fetch(url);
    const data = await res.json();
    const alerts = data.alerts || [];

    document.getElementById("subtitle").textContent =
      `${alerts.length} alert${alerts.length !== 1 ? "s" : ""} nearby`;
    document.getElementById("status-dot").style.background = "#22c55e";
    document.getElementById("last-update").textContent =
      `Updated ${new Date().toLocaleTimeString()}`;

    if (alerts.length === 0) {
      container.innerHTML = '<div class="empty">✅ No significant alerts near you right now.</div>';
      return;
    }

    container.innerHTML = alerts.slice(0, 8).map(a => {
      const level = (a.alert_level || "green").toLowerCase();
      const dist  = a.distance_km ? `${a.distance_km} km away` : a.country;
      return `
        <div class="alert-card ${level}" onclick="showBriefing(${a.event_id},'${a.event_type}','${(a.name||'').replace(/'/g,"\\'")}')">
          <div class="alert-name">
            <span class="alert-badge badge-${level}">${a.alert_level}</span>
            ${a.name}
          </div>
          <div class="alert-meta">
            <span>📍 ${dist}</span>
            <span>${a.severity_text || ""}</span>
          </div>
        </div>`;
    }).join("");

  } catch(e) {
    document.getElementById("status-dot").style.background = "#ef4444";
    container.innerHTML = `<div class="empty">❌ Cannot connect to agent.<br><small>Make sure the API is running:<br>uvicorn api.main:app --port 8000</small></div>`;
  }
}

async function showBriefing(eventId, eventType, name) {
  document.getElementById("main-view").style.display = "none";
  document.getElementById("briefing-view").style.display = "block";
  document.getElementById("briefing-text").textContent = `Loading briefing for ${name}...`;

  try {
    const res  = await fetch(`${API}/briefing/${eventType}/${eventId}`);
    const data = await res.json();
    document.getElementById("briefing-text").textContent =
      data.briefing_text || JSON.stringify(data, null, 2);
  } catch(e) {
    document.getElementById("briefing-text").textContent = "Failed to load briefing.";
  }
}

function showMain() {
  document.getElementById("briefing-view").style.display = "none";
  document.getElementById("main-view").style.display = "block";
}

function refresh() { loadAlerts(); }

init();
