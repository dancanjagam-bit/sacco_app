import React, { useCallback, useEffect, useState } from "react";
import Layout from "../components/Layout";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";

const styles = {
  page: { maxWidth: 900, margin: "0 auto", padding: "24px 16px", color: "#142235" },
  card: { background: "#fff", border: "1px solid #dce4ec", borderRadius: 14, padding: 22, marginBottom: 18 },
  field: { display: "block", width: "100%", boxSizing: "border-box", padding: 14, fontSize: 18, border: "1px solid #9baaba", borderRadius: 8, marginTop: 6 },
  button: { minHeight: 52, padding: "12px 20px", fontSize: 17, fontWeight: 700, border: 0, borderRadius: 8, background: "#126b50", color: "white", cursor: "pointer", marginTop: 14 },
};

export default function TransportCrew() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [remitAmount, setRemitAmount] = useState("");
  const [activeRemittance, setActiveRemittance] = useState(null);
  const [remitKey, setRemitKey] = useState("");
  const load = useCallback(() => api.get("transport/crew/today/").then((r) => setData(r.data)).catch(() => setError("Could not load your shift. Please retry.")), []);
  useEffect(() => { load(); }, [load]);

  async function submit(e) {
    e.preventDefault(); setError(""); setNotice("");
    const a = data?.assignment;
    if (!a) return;
    const keyName=`transport-collection-key:${user?.id}:${a.id}`;
    const clientKey=sessionStorage.getItem(keyName)||window.crypto.randomUUID();
    sessionStorage.setItem(keyName,clientKey);
    const payload = { assignment: a.id, amount, notes, client_key: clientKey };
    try {
      const r = await api.post("transport/crew/today/", payload);
      setNotice(`Collection saved: KES ${r.data.amount}. This records reported cash and does not confirm payment.`);
      sessionStorage.removeItem(keyName);
      setAmount(""); setNotes(""); await load();
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save collection. Please retry.");
    }
  }

  async function createRemittance(e){e.preventDefault();setError("");setNotice("");const a=data?.assignment;if(!a)return;const keyName=`transport-remittance-key:${user?.id}:${a.id}`;const client_key=sessionStorage.getItem(keyName)||window.crypto.randomUUID();sessionStorage.setItem(keyName,client_key);try{const r=await api.post("transport/remittances/",{assignment:a.id,amount:remitAmount,client_key});sessionStorage.removeItem(keyName);setActiveRemittance(r.data);setRemitKey(sessionStorage.getItem(`transport-payment-key:${r.data.id}`)||window.crypto.randomUUID());setNotice(`Remittance ${r.data.payment_reference} saved. Reported amount KES ${r.data.amount}; received amount KES ${r.data.received_amount}.`);await load();}catch(err){setError(err.response?.data?.detail||"Could not create remittance request.");}}
  async function startStk(r){setError("");const keyName=`transport-payment-key:${r.id}`;const client_key=sessionStorage.getItem(keyName)||remitKey||window.crypto.randomUUID();sessionStorage.setItem(keyName,client_key);try{const p=await api.post(`transport/remittances/${r.id}/stk/`,{client_key,amount:r.amount});setNotice(`M-Pesa status: ${p.data.status}. An accepted STK request is not a confirmed payment.`);await load();}catch(err){setError(err.response?.data?.detail||"M-Pesa request failed or needs staff review.");}}
  async function cashHandover(r){setError("");const keyName=`transport-cash-key:${r.id}`;const client_key=sessionStorage.getItem(keyName)||window.crypto.randomUUID();sessionStorage.setItem(keyName,client_key);try{const p=await api.post(`transport/remittances/${r.id}/cash/`,{client_key,amount:r.amount});setNotice(`Cash handover status: ${p.data.status}. A clerk must confirm receipt.`);await load();}catch(err){setError(err.response?.data?.detail||"Cash handover could not be submitted.");}}

  return <Layout><main style={styles.page}>
    <h1 style={{ fontSize: 30, marginBottom: 8 }}>Today's Shift</h1>
    <p style={{ color: "#526273", fontSize: 17 }}>View your assigned work and record reported collections.</p>
    {error && <div role="alert" style={{ ...styles.card, borderColor: "#bd3333", color: "#8b1f1f" }}>{error}</div>}
    {notice && <div role="status" style={{ ...styles.card, borderColor: "#25805d", color: "#155b40" }}>{notice}</div>}
    {!data ? <section style={styles.card} role="status">Loading shift…</section> : !data.assignment ? <section style={{ ...styles.card, borderLeft: "6px solid #b7791f" }}>
      <h2>No valid assignment for today</h2><p>{data.message}</p><p>Contact your operations supervisor or SACCO staff to report a missing or incorrect assignment.</p>
    </section> : <>
      <section style={styles.card}>
        <h2>{data.assignment.vehicle_registration} · {data.assignment.route_name}</h2>
        <p><strong>Status:</strong> <span aria-label={`Shift status ${data.assignment.status}`}>{data.assignment.status.toUpperCase()}</span></p>
        <p><strong>Driver:</strong> {data.assignment.driver_name}{data.assignment.conductor_name ? ` · Conductor: ${data.assignment.conductor_name}` : " · No conductor assigned"}</p>
        <p><strong>Starts:</strong> {new Date(data.assignment.starts_at).toLocaleString()}</p>
        {data.assignment.ends_at && <p><strong>Ends:</strong> {new Date(data.assignment.ends_at).toLocaleString()}</p>}
        <p><strong>Reported collection total:</strong> KES {data.assignment.collection_total}</p>
        <p style={{ color: "#526273" }}>{data.message}</p>
      </section>
      <section style={styles.card}>
        <h2>Remit reported amount</h2><p>Choose an amount to remit. Collections are separate, and no allocation rule is configured.</p>
        <form onSubmit={createRemittance}><label htmlFor="remittance-amount">Remittance amount (KES)</label><input id="remittance-amount" style={styles.field} type="number" min="0.01" step="0.01" required value={remitAmount} onChange={e=>setRemitAmount(e.target.value)}/><button style={styles.button}>Save remittance request</button></form>
        {data.assignment.remittances?.map(r=><div key={r.id} style={{borderTop:"1px solid #dce4ec",marginTop:16,paddingTop:14}}><p><strong>Reference:</strong> {r.payment_reference} · <strong>Status:</strong> {r.status}</p><p><strong>Reported:</strong> KES {r.reported_amount} · <strong>Received:</strong> KES {r.received_amount} · <strong>Unallocated:</strong> provider-confirmed payments await configured rules</p><button type="button" style={styles.button} onClick={()=>startStk(r)}>Request M-Pesa STK</button> <button type="button" style={{...styles.button,background:"#475569"}} onClick={()=>cashHandover(r)}>Submit cash handover</button>{r.payments.map(p=><p key={p.id}>Payment {p.method}: {p.status} · KES {p.amount}{p.receipt?` · receipt ${p.receipt}`:""}</p>)}</div>)}
      </section>
      <section style={styles.card}>
        <h2>Record Collection</h2>
        <form onSubmit={submit}>
          <label htmlFor="collection-amount">Amount (KES)</label><input id="collection-amount" style={styles.field} type="number" min="0.01" step="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)} />
          <label htmlFor="collection-notes" style={{ display: "block", marginTop: 16 }}>Notes (optional)</label><textarea id="collection-notes" style={styles.field} rows="3" maxLength="300" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <button style={styles.button} type="submit">Save collection</button>
        </form>
      </section>
      <section style={styles.card}>
        <h2>Recent Activity</h2>
        {data.assignment.collections.length ? <ul>{data.assignment.collections.map((c) => <li key={c.id}>KES {c.amount} · {new Date(c.recorded_at).toLocaleString()}{c.notes ? ` · ${c.notes}` : ""} · Reported, not settled</li>)}</ul> : <p>No collections recorded for this shift yet.</p>}
      </section>
    </>}
  </main></Layout>;
}
