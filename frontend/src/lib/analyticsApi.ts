import { api } from "./api";
import type {
  AnalyticsAvailability, AnalyticsCapacityAssessment, AnalyticsForecast,
  AnalyticsHealthScore, AnalyticsMetricDefinition, AnalyticsPage, AnalyticsReliability,
  AnalyticsRun, AnalyticsSLAMeasurement, AnalyticsSummary, AnalyticsTrend,
  CapacitySummary, ForecastSummary, ReliabilitySummary, SLASummary,
} from "./types";

function query(values: Record<string, string | number | boolean | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const analyticsApi = {
  summary: () => api<AnalyticsSummary>("/analytics/summary"),
  health: (filters: Record<string, string | number | undefined> = {}) => api<AnalyticsPage<AnalyticsHealthScore>>(`/analytics/health${query(filters)}`),
  availability: (filters: Record<string, string | number | undefined> = {}) => api<AnalyticsPage<AnalyticsAvailability>>(`/analytics/availability${query(filters)}`),
  capacity: (filters: Record<string, string | number | undefined> = {}) => api<AnalyticsPage<AnalyticsCapacityAssessment>>(`/analytics/capacity${query(filters)}`),
  slaMeasurements: (filters: Record<string, string | number | undefined> = {}) => api<AnalyticsPage<AnalyticsSLAMeasurement>>(`/analytics/SLA-measurements${query(filters)}`),
  reliability: (filters: Record<string, string | number | undefined> = {}) => api<AnalyticsPage<AnalyticsReliability>>(`/analytics/reliability${query(filters)}`),
  forecasts: (filters: Record<string, string | number | undefined> = {}) => api<AnalyticsPage<AnalyticsForecast>>(`/analytics/forecasts${query(filters)}`),
  metricDefinitions: () => api<AnalyticsPage<AnalyticsMetricDefinition>>("/analytics/metric-definitions?page_size=100"),
  runs: () => api<AnalyticsPage<AnalyticsRun>>("/analytics/runs?page_size=25"),
  capacitySummary: () => api<CapacitySummary>("/analytics/capacity-summary"),
  slaSummary: () => api<SLASummary>("/analytics/SLA-summary"),
  reliabilitySummary: () => api<ReliabilitySummary>("/analytics/reliability-summary"),
  forecastSummary: () => api<ForecastSummary>("/analytics/forecast-summary"),
  trends: (filters: {metric_key:string;entity_type:string;entity_id?:string;start:string;end:string;bucket_size:string;aggregation:string;compare_previous_period?:boolean}) => api<AnalyticsTrend>(`/analytics/trends${query(filters)}`),
  forecastReport: (metricKey?: string) => api<{report:string;generated_at:string;items:AnalyticsForecast[];total:number}>(`/analytics/forecast-report${query({metric_key:metricKey})}`),
};

export function downloadAnalyticsJson(filename: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename; anchor.click();
  URL.revokeObjectURL(url);
}
