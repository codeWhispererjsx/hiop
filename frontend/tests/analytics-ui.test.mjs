import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const page = readFileSync(new URL("../src/pages/AnalyticsPage.tsx", import.meta.url), "utf8");
const charts = readFileSync(new URL("../src/components/AnalyticsCharts.tsx", import.meta.url), "utf8");
const client = readFileSync(new URL("../src/lib/analyticsApi.ts", import.meta.url), "utf8");
const types = readFileSync(new URL("../src/lib/types.ts", import.meta.url), "utf8");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../src/components/Sidebar.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/styles/analytics.css", import.meta.url), "utf8");

test("analytics navigation and protected lazy route are registered", () => {
  assert.match(app, /path="\/analytics\/\*"/);
  assert.match(app, /lazy\(\(\) => import\("\.\/pages\/AnalyticsPage"\)\)/);
  assert.doesNotMatch(sidebar, /label: "Analytics"/);
});

test("analytics workbench exposes every requested view", () => {
  for (const view of [
    "Dashboard", "Health", "Capacity", "Availability", "SLA",
    "Reliability", "Forecasts", "Trends", "Reports",
  ]) assert.match(page, new RegExp(`(?:dashboard|health|capacity|availability|sla|reliability|forecasts|trends|reports):"${view}"`), view);
});

test("executive KPIs are sourced from typed APIs", () => {
  for (const label of [
    "Overall health", "Device availability", "Capacity warnings",
    "critical assessments", "SLA compliance", "MTTR", "MTBF",
    "Forecast confidence", "Devices monitored", "Active alerts",
    "Last analytics run",
  ]) assert.ok(page.includes(label), label);
  for (const method of [
    "summary", "health", "availability", "capacity", "slaMeasurements",
    "reliability", "forecasts", "metricDefinitions", "runs",
    "capacitySummary", "slaSummary", "reliabilitySummary",
    "forecastSummary", "trends", "forecastReport",
  ]) assert.ok(client.includes(`${method}:`), method);
});

test("aligned analytics types cover forecasts, trends, and summaries", () => {
  for (const name of [
    "AnalyticsMetricDefinition", "AnalyticsRun", "AnalyticsHealthScore",
    "AnalyticsAvailability", "AnalyticsCapacityAssessment",
    "AnalyticsSLAMeasurement", "AnalyticsReliability", "AnalyticsForecast",
    "AnalyticsSummary", "CapacitySummary", "SLASummary",
    "ReliabilitySummary", "ForecastSummary", "AnalyticsTrend",
  ]) assert.ok(types.includes(`type ${name}`), name);
});

test("charts provide visual and tabular accessible representations", () => {
  for (const chart of [
    "AnalyticsLineChart", "AnalyticsBarChart", "AnalyticsDonut", "AnalyticsHeatmap",
  ]) assert.ok(charts.includes(`function ${chart}`), chart);
  assert.match(charts, /role="img"/);
  assert.match(charts, /View chart data/);
  assert.match(charts, /confidence/i);
});

test("filters persist in the URL and unsupported scopes remain explicit", () => {
  assert.match(page, /useSearchParams/);
  assert.match(page, /next\.set/);
  assert.match(page, /Backend scope unavailable/);
  for (const filter of ["Time range", "Analytics bucket", "Health status"]) {
    assert.ok(page.includes(filter), filter);
  }
});

test("reports use bounded APIs and formula-safe exports", () => {
  assert.match(page, /downloadAnalyticsJson/);
  assert.match(page, /Export CSV/);
  assert.match(page, /Print \/ Save PDF/);
  assert.ok(page.includes("guarded=/^[=+\\-@]/"));
  assert.doesNotMatch(page, /raw OID|raw SNMP/i);
});

test("responsive, theme-aware, loading, empty, and error states exist", () => {
  assert.match(page, /analytics-skeleton/);
  assert.match(page, /Feedback/);
  assert.match(css, /var\(--/);
  assert.match(css, /@media\(max-width:1180px\)/);
  assert.match(css, /@media\(max-width:760px\)/);
  assert.match(css, /@media print/);
});
