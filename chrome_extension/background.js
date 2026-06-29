const API = "http://localhost:8000";
const POLL_MINUTES = 5;

// Poll every 5 minutes for new alerts
chrome.alarms.create("pollAlerts", { periodInMinutes: POLL_MINUTES });

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "pollAlerts") return;

  try {
    const res  = await fetch(`${API}/alerts/live?min_severity=Orange&max_results=5`);
    const data = await res.json();
    const alerts = data.alerts || [];

    // Get seen alert IDs from storage
    const stored = await chrome.storage.local.get("seenAlerts");
    const seen   = new Set(stored.seenAlerts || []);
    const newAlerts = alerts.filter(a => !seen.has(String(a.event_id)));

    if (newAlerts.length > 0) {
      // Update badge
      chrome.action.setBadgeText({ text: String(newAlerts.length) });
      chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });

      // Show notification for first new alert
      const top = newAlerts[0];
      chrome.notifications.create({
        type    : "basic",
        iconUrl : "icon.png",
        title   : `🔴 ${top.alert_level} Alert — ${top.name}`,
        message : `${top.severity_text || ""} | ${top.country}`
      });

      // Mark as seen
      newAlerts.forEach(a => seen.add(String(a.event_id)));
      chrome.storage.local.set({ seenAlerts: [...seen].slice(-100) });
    } else {
      chrome.action.setBadgeText({ text: "" });
    }
  } catch(e) {
    console.log("Disaster Agent: API not reachable", e);
  }
});
