import json
import unittest
from pathlib import Path

from generate_report import build_context, format_thousands, render_report, validate_data


DATA_PATH = Path(__file__).resolve().parent / "weekly_data.json"


def sample_data():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


class ReportGeneratorTests(unittest.TestCase):
    def test_sample_renders_without_template_placeholders(self):
        html = render_report(sample_data())
        self.assertIn("Founder Weekly Brief", html)
        self.assertIn("€48k", html)
        self.assertIn("Run a 30-minute recovery review", html)
        self.assertNotIn("{{", html)
        self.assertNotIn("{%", html)

    def test_dynamic_text_is_escaped(self):
        data = sample_data()
        data["report"]["organization"] = "Northstar <script>alert(1)</script>"
        html = render_report(data)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_optional_and_missing_metrics_render_as_unavailable(self):
        data = sample_data()
        data["report"].pop("disclaimer")
        data["report"].pop("footer_note")
        data["kpis"][0]["previous"] = None
        data["kpis"][1]["value"] = None
        data["analysis"]["pipeline_series"] = []
        data["analysis"].pop("status_counts")
        data.pop("recommendations")
        html = render_report(data)
        self.assertIn("No comparison data", html)
        self.assertIn("Not available", html)
        self.assertIn("No chart data available", html)
        self.assertIn("Project status data is not available", html)
        self.assertIn("No recommendations are available", html)
        self.assertNotIn("Illustrative demo report only", html)

    def test_missing_required_field_is_rejected(self):
        data = sample_data()
        del data["report"]["organization"]
        with self.assertRaisesRegex(ValueError, "report.organization"):
            validate_data(data)

    def test_count_metrics_reject_fractional_values(self):
        data = sample_data()
        data["analysis"]["status_counts"]["at_risk"] = 2.5
        with self.assertRaisesRegex(ValueError, "status_counts.at_risk must be a whole number"):
            validate_data(data)

    def test_status_chart_uses_zero_safe_empty_state(self):
        data = sample_data()
        data["analysis"]["status_counts"] = {"on_track": 0, "at_risk": 0, "overdue": 0}
        context = build_context(data)
        self.assertIsNone(context["status_chart"])

    def test_pipeline_chart_formats_thousand_euro_values_without_rescaling(self):
        context = build_context(sample_data())
        chart = context["pipeline_chart"]
        self.assertEqual(chart["last_value_label"], "€48k")
        self.assertIn("€18k in W35 to €48k in W42", chart["accessible_label"])
        self.assertEqual(format_thousands(37.5), "€37.5k")


if __name__ == "__main__":
    unittest.main()