import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import FormField from "../components/ui/FormField";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import { ROUTES } from "../navigation/routes";
import "../styles/loanCalculator.css";

const format = new Intl.NumberFormat("en-KE", {
  style: "currency", currency: "KES", minimumFractionDigits: 2, maximumFractionDigits: 2,
});
const money = (value) => format.format(Number(value));

export default function LoanCalculator() {
  const navigate = useNavigate();
  const [products, setProducts] = useState(null);
  const [productId, setProductId] = useState("");
  const [amount, setAmount] = useState("");
  const [months, setMonths] = useState("");
  const [estimate, setEstimate] = useState(null);
  const [error, setError] = useState("");
  const [calculating, setCalculating] = useState(false);

  const load = useCallback(async () => {
    setProducts(null);
    setError("");
    try {
      const { data } = await api.get("loan/products/");
      if (!Array.isArray(data.products)) throw new Error("Invalid product list");
      setProducts(data.products);
      setProductId(data.products[0]?.id || "");
      setMonths(String(data.products[0]?.repayment_periods[0] || ""));
    } catch {
      setError("Loan products could not be loaded. Try again.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const product = products?.find((item) => item.id === productId);

  async function calculate(event) {
    event.preventDefault();
    setEstimate(null);
    setError("");
    setCalculating(true);
    try {
      const { data } = await api.post("loan/estimate/", {
        product: productId, amount, repayment_months: Number(months),
      });
      setEstimate(data);
    } catch (err) {
      const details = err.response?.data;
      setError(details?.detail || details?.amount?.[0] || details?.repayment_months?.[0]
        || "The estimate could not be calculated. Check your inputs and try again.");
    } finally {
      setCalculating(false);
    }
  }

  return (
    <Layout>
      <main className="calc-page">
        <PageHeading title="Loan calculator"
          description="Estimate your repayments before applying. Approval and eligibility are assessed separately."
          actions={<Link className="ui-button ui-button-secondary" to={ROUTES.loans}>Back to loans</Link>} />
        {!products && !error && <LoadingState label="Loading loan products…" />}
        {error && <FeedbackMessage tone="danger" title="Estimate unavailable"
          action={!products ? <Button onClick={load}>Retry</Button> : undefined}>{error}</FeedbackMessage>}
        {products?.length === 0 && <FeedbackMessage tone="warning" title="No loan products available" />}
        {product && (
          <div className="calc-grid">
            <section className="calc-panel">
              <div className="ui-panel-header"><h2 className="ui-panel-title">Loan details</h2></div>
              <form className="calc-form" onSubmit={calculate}>
                <FormField label="Loan product" htmlFor="calc-product">
                  <select className="ui-select" id="calc-product" value={productId} disabled={calculating}
                    onChange={(event) => {
                      const selected = products.find((item) => item.id === event.target.value);
                      setProductId(selected.id);
                      setMonths(String(selected.repayment_periods[0]));
                      setEstimate(null);
                    }}>
                    {products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </FormField>
                <FormField label="Requested amount (KES)" htmlFor="calc-amount">
                  <input className="ui-input" id="calc-amount" type="number" inputMode="decimal" step="0.01"
                    min={product.minimum_amount} value={amount} required disabled={calculating}
                    onChange={(event) => { setAmount(event.target.value); setEstimate(null); }} />
                </FormField>
                <FormField label="Repayment period" htmlFor="calc-period">
                  <select className="ui-select" id="calc-period" value={months} disabled={calculating}
                    onChange={(event) => { setMonths(event.target.value); setEstimate(null); }}>
                    {product.repayment_periods.map((period) => <option key={period} value={period}>{period} months</option>)}
                  </select>
                </FormField>
                <Button type="submit" loading={calculating}>Calculate estimate</Button>
              </form>
            </section>
            {estimate && <section className="calc-panel calc-summary" aria-live="polite">
              <div className="ui-panel-header"><h2 className="ui-panel-title">Estimated repayments</h2></div>
              <div className="ui-panel-body">
                <dl className="calc-summary-facts">
                  <div><dt>Interest rate</dt><dd>{estimate.interest_rate}% for the full term</dd></div>
                  <div><dt>Calculation method</dt><dd>Flat rate on the original principal</dd></div>
                  <div><dt>Fees</dt><dd>{money(estimate.fees)}</dd></div>
                  <div><dt>Estimated first installment</dt><dd>{money(estimate.estimated_installment)}</dd></div>
                  <div><dt>Total interest</dt><dd>{money(estimate.total_interest)}</dd></div>
                  <div><dt>Total repayment</dt><dd>{money(estimate.total_repayment)}</dd></div>
                </dl>
                {estimate.application_notice && <FeedbackMessage tone="warning" title="Current application limit">{estimate.application_notice}</FeedbackMessage>}
                <Button onClick={() => navigate(ROUTES.loans, { state: {
                  prefill: { product: estimate.product, amount: estimate.amount, months: estimate.repayment_months },
                } })}>Continue to application</Button>
              </div>
            </section>}
          </div>
        )}
        {estimate && <section className="calc-panel" aria-labelledby="calc-schedule-title">
          <div className="ui-panel-header"><h2 className="ui-panel-title" id="calc-schedule-title">Estimated repayment schedule</h2></div>
          <div className="ui-table-wrap" tabIndex={0} role="region" aria-label="Estimated repayment schedule">
            <table className="ui-table">
              <thead><tr><th>Month</th><th>Principal</th><th>Interest</th><th>Installment</th><th>Remaining</th></tr></thead>
              <tbody>{estimate.schedule.map((row) => <tr key={row.month}>
                <th scope="row">{row.month}</th><td>{money(row.principal)}</td><td>{money(row.interest)}</td>
                <td>{money(row.payment)}</td><td>{money(row.remaining)}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </section>}
      </main>
    </Layout>
  );
}
