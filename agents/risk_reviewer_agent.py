"""
Risk / Reviewer Agent
----------------------
The final agent in the pipeline. Checks the assembled
briefing before it reaches any user and:

  1. Validates the briefing is complete and consistent
  2. Checks tone is not alarmist or contradictory
  3. Enforces disclaimer is present (code-level, not just prompt)
  4. Flags low-confidence briefings with a warning label
  5. Detects and neutralizes any prompt-injection attempts
     that may have come in via GDACS alert text

Input  : briefing dict from SynthesisOutputAgent
Output : reviewed briefing dict with review_report attached
"""

import re
from datetime import datetime, timezone


# ── Injection patterns to detect in briefing text ──────────
# These catch attempts to inject instructions via event names
# or descriptions from the external GDACS feed
INJECTION_PATTERNS = [
    r"ignore (previous|above|all) instructions",
    r"you are now",
    r"disregard (your|the|all)",
    r"new (instructions|prompt|system)",
    r"forget (everything|your|the)",
    r"act as",
    r"pretend (you|to)",
    r"jailbreak",
    r"do not follow",
]

# ── Words that signal potentially alarmist language ─────────
ALARMIST_WORDS = [
    "apocalyptic", "catastrophic end", "total destruction",
    "everyone will die", "no survivors", "mass extinction",
    "end of the world", "annihilation"
]

# ── Required sections in every briefing ────────────────────
REQUIRED_SECTIONS = [
    "what_happened",
    "weather",
    "impact",
    "disclaimer"
]


class RiskReviewerAgent:
    """
    Reviews and validates a briefing from SynthesisOutputAgent
    before it is shown to users or sent as a notification.

    Attaches a review_report to the briefing dict containing:
    - passed     : bool — True if briefing is safe to show
    - flags      : list of issues found
    - actions    : list of corrections applied
    - reviewed_at: timestamp
    """

    def review(self, briefing):
        """
        Main method — reviews the briefing.

        Args:
            briefing : dict from SynthesisOutputAgent.synthesize()

        Returns:
            briefing dict with review_report attached and
            any corrections applied in-place
        """
        structured = briefing.get("structured", {})
        text       = briefing.get("text", "")

        print(f"[ReviewerAgent] Reviewing briefing for: "
              f"{structured.get('event_name')}...")

        flags   = []
        actions = []

        # ── Check 1: Disclaimer present ─────────────────────
        flags, actions = self._check_disclaimer(
            structured, text, flags, actions
        )

        # ── Check 2: Required sections present ──────────────
        flags, actions = self._check_completeness(
            structured, flags, actions
        )

        # ── Check 3: Prompt injection detection ─────────────
        flags, actions = self._check_injection(
            text, flags, actions
        )

        # ── Check 4: Alarmist language ───────────────────────
        flags, actions = self._check_alarmist(
            text, flags, actions
        )

        # ── Check 5: Confidence + LLM availability ───────────
        flags, actions = self._check_confidence(
            structured, flags, actions
        )

        # ── Check 6: Alert level vs severity consistency ─────
        flags, actions = self._check_consistency(
            structured, flags, actions
        )

        # ── Determine pass/fail ─────────────────────────────
        # Hard failures = injection detected
        # Soft flags = warnings (briefing still shown with label)
        hard_flags = [f for f in flags if f["severity"] == "hard"]
        passed     = len(hard_flags) == 0

        # Attach low-confidence warning label to text if needed
        if not passed:
            briefing["text"] = (
                "⛔ THIS BRIEFING HAS BEEN BLOCKED BY THE "
                "SAFETY REVIEWER.\nReason: " +
                ", ".join(f["message"] for f in hard_flags) +
                "\n\n" + briefing["text"]
            )
        elif any(f["severity"] == "soft" for f in flags):
            briefing["text"] = (
                "⚠️  NOTE: This briefing has low confidence — "
                "LLM assessment was unavailable. "
                "Data shown is from automated sensors only.\n\n"
                + briefing["text"]
            )

        # ── Build review report ─────────────────────────────
        briefing["review_report"] = {
            "passed"     : passed,
            "flags"      : flags,
            "actions"    : actions,
            "flag_count" : len(flags),
            "hard_count" : len(hard_flags),
            "soft_count" : len(flags) - len(hard_flags),
            "reviewed_at": datetime.now(timezone.utc).isoformat()
        }

        status = "✅ PASSED" if passed else "⛔ BLOCKED"
        print(f"[ReviewerAgent] {status} — "
              f"{len(flags)} flags "
              f"({len(hard_flags)} hard, "
              f"{len(flags)-len(hard_flags)} soft)")

        return briefing

    # ── private checks ──────────────────────────────────────

    def _check_disclaimer(self, structured, text, flags, actions):
        """Enforce disclaimer is present in both structured + text."""
        disclaimer = structured.get("disclaimer", "")

        if not disclaimer:
            # Add it back (code-level enforcement)
            from agents.synthesis_output_agent import DISCLAIMER
            structured["disclaimer"] = DISCLAIMER
            text += f"\n\n{DISCLAIMER}"
            flags.append({
                "check"   : "disclaimer",
                "severity": "soft",
                "message" : "Disclaimer was missing — added automatically"
            })
            actions.append("Added missing disclaimer")
        elif "official" not in disclaimer.lower():
            flags.append({
                "check"   : "disclaimer",
                "severity": "soft",
                "message" : "Disclaimer may be insufficient"
            })

        return flags, actions

    def _check_completeness(self, structured, flags, actions):
        """Check all required sections are present."""
        for section in REQUIRED_SECTIONS:
            if section not in structured or not structured[section]:
                flags.append({
                    "check"   : "completeness",
                    "severity": "soft",
                    "message" : f"Missing section: {section}"
                })
                actions.append(f"Flagged missing section: {section}")

        return flags, actions

    def _check_injection(self, text, flags, actions):
        """
        Detect prompt injection attempts in briefing text.
        These could arrive via malicious GDACS event names
        or descriptions from the external feed.
        """
        text_lower = text.lower()
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text_lower):
                flags.append({
                    "check"   : "injection",
                    "severity": "hard",
                    "message" : (f"Possible prompt injection detected: "
                                 f"'{pattern}'")
                })
                actions.append(
                    f"Blocked briefing due to injection pattern: {pattern}"
                )

        return flags, actions

    def _check_alarmist(self, text, flags, actions):
        """Check for alarmist language that could cause panic."""
        text_lower = text.lower()
        found = [w for w in ALARMIST_WORDS if w in text_lower]

        if found:
            flags.append({
                "check"   : "alarmist_language",
                "severity": "soft",
                "message" : f"Potentially alarmist language: {found}"
            })
            actions.append(
                f"Flagged alarmist language for manual review: {found}"
            )

        return flags, actions

    def _check_confidence(self, structured, flags, actions):
        """Flag low-confidence or LLM-unavailable briefings."""
        impact = structured.get("impact", {})

        if not impact.get("llm_available", True):
            flags.append({
                "check"   : "confidence",
                "severity": "soft",
                "message" : "LLM assessment unavailable — "
                            "showing sensor data only"
            })

        elif impact.get("confidence") == "low":
            flags.append({
                "check"   : "confidence",
                "severity": "soft",
                "message" : "Low confidence assessment"
            })

        return flags, actions

    def _check_consistency(self, structured, flags, actions):
        """
        Check alert level vs assessed severity are not
        wildly contradictory (e.g. Red alert but LLM says low).
        """
        alert_level      = structured.get("alert_level", "").lower()
        overall_severity = structured.get(
            "impact", {}
        ).get("overall_severity", "").lower()

        contradictions = {
            ("red",    "low")     : True,
            ("red",    "moderate"): True,
            ("green",  "critical"): True,
        }

        if contradictions.get((alert_level, overall_severity)):
            flags.append({
                "check"   : "consistency",
                "severity": "soft",
                "message" : (
                    f"Alert level ({alert_level}) contradicts "
                    f"assessed severity ({overall_severity}) — "
                    f"review recommended"
                )
            })

        return flags, actions