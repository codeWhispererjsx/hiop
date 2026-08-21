import { useState } from "react";
import { Feedback } from "../components/Feedback";
import { PageTitle } from "../components/PageTitle";
import { StatusBadge } from "../components/StatusBadge";
import { useRequest } from "../hooks/useRequest";
import DashboardLayout from "../layouts/DashboardLayout";
import { endpoints, getPaginatedItems } from "../lib/api";
import type { BillingPlan, OrganizationSubscription } from "../lib/types";

const when = (value: string | null) =>
  value ? new Date(value).toLocaleDateString() : "Not scheduled";

const label = (value: string) =>
  value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (x) => x.toUpperCase());

export default function BillingPage() {
  const current = useRequest(endpoints.currentBilling, []);
  const plans = useRequest(endpoints.billingPlans, []);
  const documents = useRequest(endpoints.billingDocuments, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const subscription = current.data?.subscription;

  const act = async (task: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await task();
      await current.reload();
    } catch (x) {
      setError(
        x instanceof Error ? x.message : "Billing action could not be completed."
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <DashboardLayout>
      <PageTitle
        eyebrow="Administration · commercial account"
        title="Billing & subscription"
        copy="Review your organization's plan, trial, renewal, usage and commercial limits."
      />
      {error && <Feedback error={error} />}
      <section className="billing-intro" aria-label="Billing account overview">
        <div><span>Commercial account</span><strong>One subscription for the organization</strong><small>Property users inherit access from the organization plan.</small></div>
        <div><span>Secure payments</span><strong>Card details never enter HIOP</strong><small>Checkout and billing documents use the configured provider.</small></div>
        <div><span>Safe limits</span><strong>Existing records are preserved</strong><small>Reaching a limit blocks new usage; it never deletes operational data.</small></div>
      </section>
      {current.loading || current.error ? (
        <Feedback loading={current.loading} error={current.error} />
      ) : subscription ? (
        <SubscriptionView
          row={subscription}
          plans={getPaginatedItems(plans.data)}
          busy={busy}
          change={(code, interval) =>
            act(() => endpoints.changeBillingPlan(code, interval))
          }
          cancel={() => act(() => endpoints.cancelBilling(true))}
        />
      ) : (
        <section className="panel">
          <h2>No subscription configured</h2>
          <p>
            Select an available plan to begin its configured trial. No payment
            details are collected by HIOP.
          </p>
          <PlanChoices
            plans={getPaginatedItems(plans.data)}
            busy={busy}
            select={(code) => act(() => endpoints.startBillingTrial(code))}
          />
        </section>
      )}
      <section className="panel" aria-label="Billing documents">
        <h2>Billing documents</h2>
        {documents.loading || documents.error ? (
          <Feedback loading={documents.loading} error={documents.error} />
        ) : documents.data?.length ? (
          <div className="data-table">
            {documents.data.map((x) => (
              <a
                className="table-row"
                href={x.hosted_url ?? undefined}
                key={x.id}
                rel="noreferrer"
                aria-label={`View ${label(x.type)}`}
              >
                <strong>{label(x.type)}</strong>
                <span>
                  {x.amount
                    ? `${x.currency} ${x.amount}`
                    : "Amount unavailable"}
                </span>
                <span>{when(x.issued_at)}</span>
              </a>
            ))}
          </div>
        ) : (
          <p>No invoices or receipts are available.</p>
        )}
      </section>
    </DashboardLayout>
  );
}

function SubscriptionView({
  row,
  plans,
  busy,
  change,
  cancel,
}: {
  row: OrganizationSubscription;
  plans: BillingPlan[];
  busy: boolean;
  change: (code: string, interval: string) => void;
  cancel: () => void;
}) {
  const [plan, setPlan] = useState(row.plan.code);
  const [interval, setInterval] = useState(row.billing_interval);

  return (
    <>
      <section className="panel billing-current" aria-label="Current subscription details">
        <header className="section-head">
          <div>
            <span>Current plan</span>
            <h2>{row.plan.name}</h2>
            <p>
              {label(row.billing_interval)} ·{" "}
              {row.plan.monthly_price || row.plan.yearly_price
                ? `${row.plan.currency} ${
                    row.billing_interval === "monthly"
                      ? row.plan.monthly_price
                      : row.plan.yearly_price
                  }`
                : "Contact-based pricing"}
            </p>
          </div>
          <StatusBadge status={row.status} />
        </header>
        <dl className="detail-grid">
          <div>
            <dt>Payment status</dt>
            <dd>{label(row.payment_status)}</dd>
          </div>
          <div>
            <dt>Trial ends</dt>
            <dd>{when(row.trial_end)}</dd>
          </div>
          <div>
            <dt>Next renewal</dt>
            <dd>{when(row.renewal_date || row.current_period_end)}</dd>
          </div>
          <div>
            <dt>Cancellation</dt>
            <dd>
              {row.cancel_at_period_end
                ? `Scheduled ${when(row.cancellation_date)}`
                : "Not scheduled"}
            </dd>
          </div>
        </dl>
      </section>

      <section className="panel billing-usage" aria-label="Usage and limits">
        <h2>Usage and limits</h2>
        <div className="usage-grid">
          {Object.entries(row.usage).map(([key, value]) => (
            <article className="usage-card" key={key}>
              <span>{label(key)}</span>
              <strong>
                {value} / {row.limits[key] ?? "Unlimited"}
              </strong>
              {row.over_limits[key] && (
                <small className="usage-warning">Current usage exceeds this plan.</small>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="panel billing-management" aria-label="Plan management">
        <h2>Manage plan</h2>
        <div className="form-grid">
          <label htmlFor="billing-plan">
            Plan
            <select
              id="billing-plan"
              value={plan}
              onChange={(e) => setPlan(e.target.value)}
            >
              {plans
                .filter((x) => x.is_active)
                .map((x) => (
                  <option value={x.code} key={x.id}>
                    {x.name}
                  </option>
                ))}
            </select>
          </label>
          <label htmlFor="billing-interval">
            Billing interval
            <select
              id="billing-interval"
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
            >
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
            </select>
          </label>
        </div>
        <div className="row-actions">
          <button
            className="primary-action"
            disabled={
              busy ||
              (plan === row.plan.code && interval === row.billing_interval)
            }
            onClick={() => change(plan, interval)}
            aria-busy={busy}
          >
            {busy ? "Updating…" : "Change plan"}
          </button>
          {!row.cancel_at_period_end && (
            <button
              className="danger-action"
              disabled={busy}
              onClick={cancel}
              aria-label="Cancel subscription"
              aria-busy={busy}
            >
              {busy ? "Processing…" : "Cancel at period end"}
            </button>
          )}
        </div>
      </section>
    </>
  );
}

function PlanChoices({
  plans,
  busy,
  select,
}: {
  plans: BillingPlan[];
  busy: boolean;
  select: (code: string) => void;
}) {
  return (
    <div className="admin-access-grid">
      {plans.map((x) => (
        <article className="panel" key={x.id}>
          <h3>{x.name}</h3>
          <p>{x.description}</p>
          <small>{x.trial_days} day trial</small>
          <button
            className="primary-action"
            disabled={busy}
            onClick={() => select(x.code)}
            aria-label={`Start trial for ${x.name}`}
            aria-busy={busy}
          >
            {busy ? "Starting…" : "Start trial"}
          </button>
        </article>
      ))}
    </div>
  );
}
