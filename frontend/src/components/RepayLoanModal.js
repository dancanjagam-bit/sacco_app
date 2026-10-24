import React, { useState } from "react";
import api from "../api/axios";

function RepayLoanModal({
  loan,
  onClose,
  onUpdated,
}) {
  const [amount, setAmount] = useState("");
  const [saving, setSaving] = useState(false);

  const repayLoan = async () => {
    if (!amount) {
      alert("Enter a repayment amount.");
      return;
    }

    setSaving(true);

    try {
      await api.post(
        `loan/${loan.id}/repay/`,
        {
          amount,
        }
      );

      alert("Repayment successful.");

      onUpdated();
      onClose();
    } catch (err) {
      alert(
        err.response?.data?.error ||
        "Repayment failed."
      );
    }

    setSaving(false);
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.5)",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          background: "#fff",
          padding: 25,
          borderRadius: 10,
          width: 400,
        }}
      >
        <h2>Repay Loan</h2>

        <p>
          Outstanding Balance:
          <strong>
            {" "}KES {loan.balance}
          </strong>
        </p>

        <label>Repayment Amount</label>

        <input
          type="number"
          value={amount}
          onChange={(e) =>
            setAmount(e.target.value)
          }
          style={{ width: "100%" }}
        />

        <br />
        <br />

        <button
          onClick={repayLoan}
          disabled={saving}
        >
          {saving
            ? "Processing..."
            : "Make Repayment"}
        </button>

        <button
          onClick={onClose}
          style={{ marginLeft: 10 }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export default RepayLoanModal;
