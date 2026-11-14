import React from "react";
import Layout from "../components/Layout";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import PageHeading from "../components/ui/PageHeading";

export default function StaffFeatureUnavailable({ feature = "this task" }) {
  return <Layout><main className="staff-workspace-page">
    <PageHeading eyebrow="Credit review" title="Arrears review" description="Assigned loan decisions and membership records remain available in their own work areas." />
    <FeedbackMessage tone="warning" title={`${feature[0].toUpperCase()}${feature.slice(1)} is not available yet`}>
      The application does not have a validated, persisted installment ledger for staff arrears review. Member schedules are derived from loan terms and repayment entries and are not suitable as a reconciliation-grade delinquency report. No overdue amount or status is inferred here.
    </FeedbackMessage>
  </main></Layout>;
}
