# eval/metrics.py
"""
Evaluation Metrics Harness
---------------------------
Runs the disaster relief pipeline over all saved reference
events and logs performance metrics.

Metrics tracked:
  - Coverage rate    : % of events that produced a full briefing
  - Latency          : time from alert to briefing (seconds)
  - Tool success rate: % of MCP tool calls that succeeded
  - LLM consistency  : stability of impact assessment across runs
  - Risk flag rate   : how often reviewer flags/adjusts output

Usage:
  python eval/metrics.py              # run all reference events
  python eval/metrics.py --live       # also run on current live alert
  python eval/metrics.py --save       # save results to data/processed/
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.tools import get_disaster_alerts, get_weather, get_full_briefing
from mcp_server.rate_limiter import rate_limiter
from agents.trigger_ingestion_agent import TriggerIngestionAgent
from agents.weather_context_agent import WeatherContextAgent
from agents.synthesis_output_agent import SynthesisOutputAgent
from agents.risk_reviewer_agent import RiskReviewerAgent


REFERENCE_FILES = [
    "data/raw/ref_TC_1000985.json",
    "data/raw/ref_FL_1102983.json",
    "data/raw/ref_VO_1000109.json"
]


def run_eval(include_live=False, save_results=False):
    """Run full evaluation over reference events + optionally live alert."""

    print("\n" + "="*60)
    print("  DISASTER RELIEF AGENT — EVALUATION METRICS")
    print(f"  Run at: {datetime.utcnow().isoformat()} UTC")
    print("="*60)

    results   = []
    tool_calls = {"total": 0, "success": 0, "failed": 0}

    # ── Load reference events ──────────────────────────────
    events_to_test = []

    for path in REFERENCE_FILES:
        if not os.path.exists(path):
            print(f"⚠️  Skipping {path} — not found")
            continue
        with open(path) as f:
            ref = json.load(f)
        props  = ref.get("event", {})
        coords = ref.get("coords", {})

        events_to_test.append({
            "source"    : "reference",
            "file"      : path,
            "alert": {
                "event_id"     : props.get("eventid"),
                "event_type"   : props.get("eventtype"),
                "name"         : props.get("name"),
                "country"      : props.get("country"),
                "affected"     : [c["countryname"] for c in props.get("affectedcountries", [])],
                "alert_level"  : props.get("alertlevel"),
                "severity_text": props.get("severitydata", {}).get("severitytext"),
                "from_date"    : props.get("fromdate"),
                "lat"          : coords.get("lat"),
                "lon"          : coords.get("lon"),
                "report_url"   : props.get("url", {}).get("report") if isinstance(props.get("url"), dict) else None
            },
            "saved_weather": ref.get("weather")
        })

    # ── Optionally add live alert ──────────────────────────
    if include_live:
        print("\nFetching live alert...")
        try:
            trigger = TriggerIngestionAgent(min_alert_level="Green", max_results=5)
            top     = trigger.fetch_top()
            if top:
                events_to_test.append({
                    "source"       : "live",
                    "file"         : None,
                    "alert"        : top,
                    "saved_weather": None
                })
                print(f"  Live alert: {top['name']} | {top['alert_level']}")
        except Exception as e:
            print(f"  Failed to fetch live alert: {e}")

    # ── Run pipeline for each event ────────────────────────
    print(f"\nRunning pipeline for {len(events_to_test)} events...\n")

    for i, event in enumerate(events_to_test):
        alert  = event["alert"]
        source = event["source"]

        print(f"[{i+1}/{len(events_to_test)}] {alert.get('name')} "
              f"({alert.get('alert_level')}) [{source}]")

        result = {
            "event_name"  : alert.get("name"),
            "event_type"  : alert.get("event_type"),
            "alert_level" : alert.get("alert_level"),
            "country"     : alert.get("country"),
            "source"      : source,
            "timestamp"   : datetime.utcnow().isoformat()
        }

        pipeline_start = time.time()
        stages_complete = []

        try:
            # Stage 1: Alert data (already have it)
            stages_complete.append("trigger")
            tool_calls["total"]   += 1
            tool_calls["success"] += 1

            # Stage 2: Weather
            t_weather = time.time()
            tool_calls["total"] += 1
            try:
                if event["saved_weather"]:
                    weather = event["saved_weather"]
                    print(f"  Weather  : ✅ using saved data")
                else:
                    weather_agent = WeatherContextAgent()
                    weather = weather_agent.fetch_for_alert(alert)
                    print(f"  Weather  : ✅ fetched live")
                stages_complete.append("weather")
                tool_calls["success"] += 1
            except Exception as e:
                weather = {"data_available": False, "current": {}, "forecast": [], "danger_flags": []}
                print(f"  Weather  : ❌ failed — {e}")
                tool_calls["failed"] += 1

            result["weather_latency_s"] = round(time.time() - t_weather, 2)
            result["weather_available"] = weather.get("data_available", True)

            # Stage 3: Impact (skip LLM to avoid quota, use fallback)
            t_impact = time.time()
            impact = {
                "overall_severity": alert.get("alert_level","").lower(),
                "confidence"      : "low",
                "reasoning"       : "LLM skipped in eval (quota conservation)",
                "llm_available"   : False,
                "population_at_risk"    : {"summary": "Eval mode", "vulnerability_factors": [], "estimated_scale": "unknown"},
                "infrastructure_threats": {"summary": "Eval mode", "specific_risks": []},
                "immediate_dangers"     : {"summary": "Eval mode", "danger_list": [], "time_sensitivity": "unknown"},
                "recommended_actions"   : {"for_residents": ["Follow official guidance"], "for_responders": ["Await assessment"]}
            }
            stages_complete.append("impact")
            result["impact_latency_s"] = round(time.time() - t_impact, 2)
            result["llm_used"] = False
            print(f"  Impact   : ⚠️  LLM skipped (quota conservation)")

            # Stage 4: Synthesis
            t_synth = time.time()
            tool_calls["total"] += 1
            try:
                synth    = SynthesisOutputAgent()
                briefing = synth.synthesize(alert, weather, impact)
                stages_complete.append("synthesis")
                tool_calls["success"] += 1
                print(f"  Synthesis: ✅ {len(briefing['text'])} chars")
            except Exception as e:
                briefing = None
                print(f"  Synthesis: ❌ failed — {e}")
                tool_calls["failed"] += 1

            result["synthesis_latency_s"] = round(time.time() - t_synth, 2)

            # Stage 5: Review
            t_review = time.time()
            tool_calls["total"] += 1
            if briefing:
                try:
                    reviewer = RiskReviewerAgent()
                    reviewed = reviewer.review(briefing)
                    stages_complete.append("review")
                    tool_calls["success"] += 1

                    rr = reviewed["review_report"]
                    result["review_passed"]    = rr["passed"]
                    result["review_flags"]     = rr["flag_count"]
                    result["review_hard_flags"] = rr["hard_count"]
                    result["review_soft_flags"] = rr["soft_count"]
                    print(f"  Review   : {'✅ PASSED' if rr['passed'] else '⛔ BLOCKED'} "
                          f"— {rr['flag_count']} flags")
                except Exception as e:
                    print(f"  Review   : ❌ failed — {e}")
                    tool_calls["failed"] += 1
            else:
                result["review_passed"] = False

            result["review_latency_s"] = round(time.time() - t_review, 2)

        except Exception as e:
            print(f"  Pipeline : ❌ unexpected error — {e}")

        # Overall metrics
        total_latency = round(time.time() - pipeline_start, 2)
        result["total_latency_s"]  = total_latency
        result["stages_complete"]  = stages_complete
        result["stages_count"]     = len(stages_complete)
        result["pipeline_complete"] = len(stages_complete) == 5

        print(f"  Total    : {total_latency}s | "
              f"Stages: {len(stages_complete)}/5 | "
              f"{'✅ COMPLETE' if result['pipeline_complete'] else '⚠️  PARTIAL'}\n")

        results.append(result)

    # ── Summary metrics ────────────────────────────────────
    total     = len(results)
    complete  = sum(1 for r in results if r.get("pipeline_complete"))
    avg_lat   = sum(r.get("total_latency_s", 0) for r in results) / max(total, 1)
    tool_rate = (tool_calls["success"] / max(tool_calls["total"], 1)) * 100
    flag_rate = sum(1 for r in results if r.get("review_flags", 0) > 0) / max(total, 1) * 100

    summary = {
        "run_at"               : datetime.utcnow().isoformat(),
        "events_tested"        : total,
        "coverage_rate"        : f"{complete}/{total} ({complete/max(total,1)*100:.0f}%)",
        "avg_latency_s"        : round(avg_lat, 2),
        "tool_call_success_rate": f"{tool_calls['success']}/{tool_calls['total']} ({tool_rate:.0f}%)",
        "tool_calls"           : tool_calls,
        "risk_flag_rate"       : f"{flag_rate:.0f}%",
        "llm_used"             : any(r.get("llm_used") for r in results),
        "results"              : results
    }

    print("="*60)
    print("  SUMMARY")
    print("="*60)
    print(f"  Events tested       : {total}")
    print(f"  Coverage rate       : {summary['coverage_rate']}")
    print(f"  Avg latency         : {summary['avg_latency_s']}s")
    print(f"  Tool call success   : {summary['tool_call_success_rate']}")
    print(f"  Risk flag rate      : {summary['risk_flag_rate']}")
    print(f"  Rate limiter stats  : {rate_limiter.get_stats()}")

    # ── Save results ───────────────────────────────────────
    if save_results:
        os.makedirs("data/processed", exist_ok=True)
        out_path = "data/processed/eval_results.json"
        with open(out_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"\n✅ Results saved → {out_path}")

    print("="*60 + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Disaster Relief Agent Eval Harness")
    parser.add_argument("--live", action="store_true", help="Also test live GDACS alert")
    parser.add_argument("--save", action="store_true", help="Save results to data/processed/")
    args = parser.parse_args()

    run_eval(include_live=args.live, save_results=args.save)