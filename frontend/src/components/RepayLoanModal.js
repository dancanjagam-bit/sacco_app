import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import MpesaPayModal from "./MpesaPayModal";
import Button from "./ui/Button";
import FeedbackMessage from "./ui/FeedbackMessage";
import FormField from "./ui/FormField";
import "../styles/repay-modal.css";

export default function RepayLoanModal({ loan, onClose, onUpdated }) {
  const { user } = useAuth();
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [reviewAmount, setReviewAmount] = useState(null);
  const value = Number(amount);
  const recordedBalance = loan.balance === null || loan.balance === undefined || loan.balance === ""
    ? "Unavailable"
    : Number.isFinite(Number(loan.balance))
      ? `KES ${Number(loan.balance).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : "Unavailable";

  const continueToPayment = () => {
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter a repayment amount greater than zero.");
      return;
    }
    setError("");
    setReviewAmount(value);
  };

  if (reviewAmount !== null) {
    return <MpesaPayModal
      paymentType="repayment"
      amount={reviewAmount}
      loanId={loan.id}
      defaultPhone={user?.phone_number || ""}
      onClose={onClose}
      onConfirmed={onUpdated}
    />;
  }

  return (
    <div className="repay-modal-overlay" role="presentation">
      <section className="ui-panel repay-modal" role="dialog" aria-modal="true" aria-labelledby="repay-modal-title">
        <header className="repay-modal-header"><div><p className="ui-eyebrow">Loan repayment</p><h2 id="repay-modal-title">Repay a loan</h2></div><Button variant="quiet" aria-label="Close repayment" onClick={onClose}>×</Button></header>
        <div className="repay-modal-body">
          <dl className="repay-loan-summary"><div><dt>Loan</dt><dd>#{loan.id}</dd></div><div><dt>Recorded balance</dt><dd>{recordedBalance}</dd></div></dl>
          <FormField label="Repayment amount (KES)" htmlFor="repayment-amount" hint="The payment will remain pending until the provider confirms receipt." error={error}>
            <input id="repayment-amount" className="ui-input" type="number" min="1" step="1" inputMode="decimal" value={amount} onChange={(event) => { setAmount(event.target.value); setError(""); }} />
          </FormField>
          <FeedbackMessage>Review the amount before continuing. Starting a request does not reduce your balance or confirm payment.</FeedbackMessage>
          <div className="repay-modal-actions"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="accent" onClick={continueToPayment}>Continue to M-Pesa</Button></div>
        </div>
      </section>
    </div>
  );
}
