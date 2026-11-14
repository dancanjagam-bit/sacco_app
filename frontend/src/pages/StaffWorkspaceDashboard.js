import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import LoadingState from "../components/ui/LoadingState";
import MetricCard from "../components/ui/MetricCard";
import PageHeading from "../components/ui/PageHeading";
import StatusBadge from "../components/ui/StatusBadge";
import Icon from "../components/ui/Icon";
import { ROUTES } from "../navigation/routes";
import "../styles/staffWorkspaces.css";

const WORKSPACE = {
  staff: {
    title: "System administration", eyebrow: "Access management",
    description: "Manage application roles and time-bounded work assignments. Job workspaces require separate explicit grants.",
    actions: [["Manage roles and scoped duties", ROUTES.adminAccess, "shield", "staff.manage"]],
  },
  clerk: {
    title: "Transport clerk", eyebrow: "Assigned operations",
    description: "Only transport duties assigned to your account appear here.",
    actions: [
      ["View assigned transport work", ROUTES.staffClerkAssignments, "truck", "transport.assignments.manage_assigned"],
      ["Review assignment issues", ROUTES.staffClerkIssues, "alert", "transport.issues.review_assigned"],
      ["Confirm a cash handover", ROUTES.staffClerkCash, "receipt", "transport.cash_confirm_assigned"],
    ],
  },
  credit_officer: {
    title: "Credit officer", eyebrow: "Assigned credit reviews",
    description: "Review only applications assigned to you. Appraisal does not approve or disburse a loan.",
    actions: [
      ["Review assigned applications", ROUTES.adminLoans, "bank", "loans.appraise_assigned"],
      ["Arrears and delinquency", ROUTES.adminArrears, "alert", "loans.appraise_assigned"],
      ["Review assigned credit reports", ROUTES.adminCrbChecks, "shield", "loans.appraise_assigned"],
    ],
  },
  treasurer: {
    title: "Treasury", eyebrow: "Reconciliation and accounts",
    description: "Reported payments remain separate from confirmed receipts and account allocations.",
    actions: [
      ["Open payment reconciliation", ROUTES.adminReconciliation, "receipt", "payments.reconcile"],
      ["Welfare payout queue", ROUTES.staffTreasuryWelfare, "heart", "payments.reconcile"],
      ["Review transport expenses", ROUTES.adminTransportExpenses, "wallet", "transport.expenses.review"],
      ["View financial reports", ROUTES.adminFinancialReports, "file", "reports.financial.read"],
    ],
  },
  secretary: {
    title: "Secretary", eyebrow: "Membership and documents",
    description: "Membership approval, identity verification, meetings, and member notices are separate responsibilities.",
    actions: [
      ["Review membership applications", ROUTES.adminMembers, "users", "members.review"],
      ["Membership approval workflow", ROUTES.secretaryApprovals, "users", "membership.approve"],
      ["Review identity documents", ROUTES.adminIdVerifications, "id", "kyc.review"],
      ["Schedule and record meetings", ROUTES.secretaryMeetings, "file", "members.review"],
      ["Manage member notices", ROUTES.secretaryNotices, "bell", "members.review"],
    ],
  },
  chairman: {
    title: "Chairman", eyebrow: "Cooperative oversight",
    description: "Operational summaries and decisions assigned to you. This workspace does not grant general payment or reconciliation authority.",
    actions: [
      ["Review assigned loan decisions", ROUTES.adminLoans, "bank", "loans.approve_assigned"],
    ],
  },
  welfare_officer: {
    title: "Welfare officer", eyebrow: "Welfare review",
    description: "Review support requests, request additional information, approve or reject with reasons, and track payout status.",
    actions: [
      ["Open welfare review queue", ROUTES.staffWelfare, "heart", "welfare.review"],
    ],
  },
};

export default function StaffWorkspaceDashboard({ workspace }) {
  const { user } = useAuth();
  const config = WORKSPACE[workspace];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await api.get(`staff/workspaces/${workspace}/summary/`);
      if (response.data?.workspace !== workspace || !Array.isArray(response.data?.metrics) || !Array.isArray(response.data?.unavailable)) {
        throw new Error("The workspace response was incomplete.");
      }
      setData(response.data);
    } catch (requestError) {
      const status = requestError.response?.status;
      setError(status === 403
        ? "This workspace is no longer assigned to your account. Refresh your session or contact an administrator."
        : status === 503
          ? "Workspace assignments are not available until the database role migration is applied."
          : "Workspace information could not be loaded. Try again.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  useEffect(() => { load(); }, [load]);

  if (!config) return null;
  const actions = config.actions.filter(([, , , permission]) => user?.permissions?.includes(permission));

  return (
    <Layout>
      <div className="staff-workspace-page">
        <PageHeading
          eyebrow={config.eyebrow}
          title={config.title}
          description={config.description}
          actions={(
            <>
              <StatusBadge status="active" label={`${config.title} workspace`} />
              <Button variant="secondary" onClick={load} loading={loading}>
                <Icon name="refresh" size={16} /> Refresh
              </Button>
            </>
          )}
        />

        {error && <FeedbackMessage tone="danger" title="Workspace unavailable" action={<Button variant="secondary" onClick={load} loading={loading}>Retry</Button>}>{error}</FeedbackMessage>}
        {loading && !data && <LoadingState label={`Loading ${config.title.toLowerCase()} work…`} />}

        {data && (
          <>
            <section className="staff-workspace-metrics" aria-label={`${config.title} summary`}>
              {data.metrics.map((metric, index) => (
                <MetricCard
                  key={metric.id}
                  label={metric.label}
                  value={metric.value}
                  helper={workspace === "staff" ? "Current access records" : workspace === "chairman" ? "Cooperative oversight" : "Visible within your assignment"}
                  icon={["file", "receipt", "users"][index % 3]}
                />
              ))}
            </section>

            <section className="staff-workspace-actions" aria-labelledby="staff-workspace-actions-title">
              <div className="ui-panel-header">
                <div>
                  <h2 className="ui-panel-title" id="staff-workspace-actions-title">Your work</h2>
                  <p className="staff-workspace-caption">Open a task area available to your account.</p>
                </div>
              </div>
              {actions.length ? (
                <div className="staff-workspace-action-grid">
                  {actions.map(([label, to, icon]) => (
                    <Link className="staff-workspace-action" to={to} key={to}>
                      <span className="staff-workspace-action-icon"><Icon name={icon} size={20} /></span>
                      <span>{label}</span>
                      <Icon name="arrowRight" size={16} />
                    </Link>
                  ))}
                </div>
              ) : <p className="ui-empty">No task area is currently enabled for this role.</p>}
            </section>

            {data.unavailable.length > 0 && (
              <section className="staff-workspace-gaps" aria-labelledby="staff-workspace-gaps-title">
                <h2 id="staff-workspace-gaps-title">Not available yet</h2>
                <ul>{data.unavailable.map((gap) => <li key={gap}>{gap}</li>)}</ul>
              </section>
            )}
          </>
        )}
      </div>
    </Layout>
  );
}
