import React from "react";
import { Link } from "react-router-dom";
import Button from "./ui/Button";
import FeedbackMessage from "./ui/FeedbackMessage";

export default function RouteAccessDenied({ destination }) {
  return (
    <main className="application-loading">
      <div className="route-access-denied">
        <FeedbackMessage tone="warning" title="This page is not available to your account">
          Your workspace access does not include this page. If you believe this is incorrect, contact SACCO staff.
        </FeedbackMessage>
        {destination && (
          <Button as={Link} to={destination} variant="secondary">Open your workspace</Button>
        )}
      </div>
    </main>
  );
}
