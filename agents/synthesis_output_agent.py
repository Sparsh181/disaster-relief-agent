"""
Synthesis / Output Agent
--------------------------
Takes the outputs from all upstream agents:
  - TriggerIngestionAgent  → alert dict
  - WeatherContextAgent    → weather dict
  - HumanitarianImpactAgent → impact dict

And combines them into a single clean, plain-language
briefing that a non-technical person can read and act on.

No LLM call needed here — this is pure assembly/formatting.

Input  : alert dict + weather dict + impact dict
Output : structured briefing dict + formatted text string
"""

from datetime import datetime, timezone

# ── Alert level → emoji + display label ────────────────────
ALERT_DISPLAY = {
    "Red"   : ("🔴", "RED ALERT"),
    "Orange": ("🟠", "ORANGE ALERT"),
    "Green" : ("🟢", "GREEN ALERT"),
}

# ── Event type → emoji ──────────────────────────────────────
EVENT_EMOJI = {
    "EQ": "🌍",
    "TC": "🌀",
    "FL": "🌊",
    "VO": "🌋",
    "WF": "🔥",
    "DR": "☀️",
}

# ── Severity → urgency label ────────────────────────────────
SEVERITY_URGENCY = {
    "critical": "⚠️  URGENT — Immediate action required",
    "high"    : "⚠️  HIGH — Take precautions now",
    "moderate": "ℹ️  MODERATE — Stay informed and prepared",
    "low"     : "ℹ️  LOW — Monitor situation",
    "unknown" : "ℹ️  — Severity under assessment",
}

DISCLAIMER = (
    "⚠️  This is a supplementary informational briefing generated "
    "by an automated AI agent. Always follow official guidance from "
    "your local emergency management agency and government authorities."
)


class SynthesisOutputAgent:
    """
    Assembles a complete disaster briefing from the outputs
    of all upstream agents in the pipeline.

    Produces both:
    - A structured dict (for storage in DB, API responses,
      Chrome extension, dashboard)
    - A formatted plain-text string (for email notifications,
      CLI output, video demo)
    """

    def synthesize(self, alert, weather, impact):
        """
        Main method — assembles the full briefing.

        Args:
            alert   : dict from TriggerIngestionAgent
            weather : dict from WeatherContextAgent
            impact  : dict from HumanitarianImpactAgent

        Returns:
            dict with keys:
              - structured : machine-readable briefing dict
              - text       : human-readable plain text briefing
              - metadata   : generation info
        """
        print(f"[SynthesisAgent] Assembling briefing for: "
              f"{alert.get('name')}...")

        structured = self._build_structured(alert, weather, impact)
        text       = self._build_text(structured)

        result = {
            "structured"   : structured,
            "text"         : text,
            "metadata"     : {
                "event_id"    : alert.get("event_id"),
                "event_type"  : alert.get("event_type"),
                "country"     : alert.get("country"),
                "alert_level" : alert.get("alert_level"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "llm_used"    : impact.get("llm_available", True),
                "pipeline_stages": [
                    "trigger_ingestion",
                    "weather_context",
                    "humanitarian_impact",
                    "synthesis_output"
                ]
            }
        }

        print(f"[SynthesisAgent] ✅ Briefing assembled — "
              f"{len(text)} characters")
        return result

    # ── private helpers ────────────────────────────────────

    def _build_structured(self, alert, weather, impact):
        """
        Builds a structured dict — used by API, DB, extension.
        """
        alert_emoji, alert_label = ALERT_DISPLAY.get(
            alert.get("alert_level", "Green"), ("🟢", "GREEN ALERT")
        )
        event_emoji = EVENT_EMOJI.get(alert.get("event_type", ""), "🌐")
        current     = weather.get("current", {})
        forecast    = weather.get("forecast", [])

        return {
            # Header
            "title"        : (f"{event_emoji} {alert.get('name')} — "
                              f"{alert_label}"),
            "event_name"   : alert.get("name"),
            "country"      : alert.get("country"),
            "alert_level"  : alert.get("alert_level"),
            "alert_emoji"  : alert_emoji,
            "event_type"   : alert.get("event_type"),
            "event_emoji"  : event_emoji,
            "severity_text": alert.get("severity_text"),
            "from_date"    : alert.get("from_date"),
            "lat"          : alert.get("lat"),
            "lon"          : alert.get("lon"),
            "report_url"   : alert.get("report_url"),

            # What happened
            "what_happened": (
                f"{alert.get('name')} has been recorded with "
                f"{alert.get('severity_text', 'unknown severity')}. "
                f"The GDACS alert level is {alert.get('alert_level')}."
            ),

            # Weather context
            "weather": {
                "current_temp_c"  : current.get("temp_c"),
                "current_wind_kmh": current.get("wind_kmh"),
                "current_condition": current.get("condition"),
                "danger_flags"    : weather.get("danger_flags", []),
                "forecast"        : forecast,
                "data_available"  : weather.get("data_available", True)
            },

            # Impact assessment (from LLM agent)
            "impact": {
                "overall_severity"     : impact.get("overall_severity",
                                                    "unknown"),
                "urgency_label"        : SEVERITY_URGENCY.get(
                    impact.get("overall_severity", "unknown"),
                    SEVERITY_URGENCY["unknown"]
                ),
                "confidence"           : impact.get("confidence", "low"),
                "population_summary"   : impact.get(
                    "population_at_risk", {}
                ).get("summary", "Assessment unavailable"),
                "vulnerability_factors": impact.get(
                    "population_at_risk", {}
                ).get("vulnerability_factors", []),
                "estimated_scale"      : impact.get(
                    "population_at_risk", {}
                ).get("estimated_scale", "unknown"),
                "infrastructure_summary": impact.get(
                    "infrastructure_threats", {}
                ).get("summary", "Assessment unavailable"),
                "infrastructure_risks" : impact.get(
                    "infrastructure_threats", {}
                ).get("specific_risks", []),
                "danger_summary"       : impact.get(
                    "immediate_dangers", {}
                ).get("summary", "Assessment unavailable"),
                "danger_list"          : impact.get(
                    "immediate_dangers", {}
                ).get("danger_list", []),
                "time_sensitivity"     : impact.get(
                    "immediate_dangers", {}
                ).get("time_sensitivity", "unknown"),
                "actions_residents"    : impact.get(
                    "recommended_actions", {}
                ).get("for_residents", []),
                "actions_responders"   : impact.get(
                    "recommended_actions", {}
                ).get("for_responders", []),
                "reasoning"            : impact.get("reasoning", ""),
                "llm_available"        : impact.get("llm_available", True)
            },

            # Disclaimer (always present, code-enforced)
            "disclaimer": DISCLAIMER
        }

    def _build_text(self, s):
        """
        Builds a human-readable plain-text briefing string.
        Used for email notifications and CLI output.
        """
        lines = []

        # ── Header ──────────────────────────────────────────
        lines.append("=" * 60)
        lines.append(f"  {s['title']}")
        lines.append("=" * 60)
        lines.append(f"  {s['impact']['urgency_label']}")
        lines.append(f"  Generated: {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')}")
        lines.append(f"  Location : {s['country']} "
                     f"({s['lat']}, {s['lon']})")
        if s.get("report_url"):
            lines.append(f"  Source   : {s['report_url']}")
        lines.append("")

        # ── What happened ───────────────────────────────────
        lines.append("WHAT HAPPENED")
        lines.append("-" * 40)
        lines.append(s["what_happened"])
        lines.append("")

        # ── Current weather ─────────────────────────────────
        w = s["weather"]
        if w["data_available"]:
            lines.append("CONDITIONS ON THE GROUND")
            lines.append("-" * 40)
            lines.append(
                f"Current: {w['current_temp_c']}°C | "
                f"{w['current_wind_kmh']} km/h winds | "
                f"{w['current_condition']}"
            )
            if w["danger_flags"]:
                lines.append(
                    f"⚠️  Danger flags: {', '.join(w['danger_flags'])}"
                )
            if w["forecast"]:
                lines.append("\n3-Day Forecast:")
                for day in w["forecast"]:
                    lines.append(
                        f"  {day['date']}: "
                        f"Max {day['temp_max_c']}°C | "
                        f"Rain {day['precip_mm']}mm | "
                        f"Wind {day['wind_max_kmh']} km/h | "
                        f"{day['condition']}"
                    )
            lines.append("")

        # ── Who is at risk ──────────────────────────────────
        imp = s["impact"]
        lines.append("WHO IS AT RISK")
        lines.append("-" * 40)
        lines.append(imp["population_summary"])
        if imp["vulnerability_factors"]:
            lines.append("Vulnerability factors:")
            for f in imp["vulnerability_factors"]:
                lines.append(f"  • {f}")
        lines.append(f"Scale: {imp['estimated_scale'].upper()}")
        lines.append("")

        # ── Infrastructure ──────────────────────────────────
        lines.append("INFRASTRUCTURE THREATS")
        lines.append("-" * 40)
        lines.append(imp["infrastructure_summary"])
        if imp["infrastructure_risks"]:
            for r in imp["infrastructure_risks"]:
                lines.append(f"  • {r}")
        lines.append("")

        # ── Immediate dangers ───────────────────────────────
        lines.append("IMMEDIATE DANGERS")
        lines.append("-" * 40)
        lines.append(imp["danger_summary"])
        if imp["danger_list"]:
            for d in imp["danger_list"]:
                lines.append(f"  ⚠️  {d}")
        lines.append(f"Time sensitivity: {imp['time_sensitivity'].upper()}")
        lines.append("")

        # ── What to do ──────────────────────────────────────
        lines.append("WHAT YOU SHOULD DO")
        lines.append("-" * 40)
        if imp["actions_residents"]:
            lines.append("For residents:")
            for a in imp["actions_residents"]:
                lines.append(f"  → {a}")
        if imp["actions_responders"]:
            lines.append("\nFor emergency responders:")
            for a in imp["actions_responders"]:
                lines.append(f"  → {a}")
        lines.append("")

        # ── Reasoning ───────────────────────────────────────
        if imp["reasoning"] and imp.get("llm_available", True):
            lines.append("ASSESSMENT REASONING")
            lines.append("-" * 40)
            lines.append(imp["reasoning"])
            lines.append(f"Confidence: {imp['confidence'].upper()}")
            lines.append("")

        # ── Disclaimer (always last, code-enforced) ─────────
        lines.append("=" * 60)
        lines.append(s["disclaimer"])
        lines.append("=" * 60)

        return "\n".join(lines)