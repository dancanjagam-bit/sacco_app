import React, { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";

import api from "../api/axios";
import Layout from "../components/Layout";
import EditMemberModal from "../components/EditMemberModal";

import "../styles/dashboard.css";

function MemberProfile() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [member, setMember] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);

  const fetchMember = useCallback(async () => {
    try {
      const res = await api.get(`members/${id}/`);
      setMember(res.data);
    } catch (err) {
      console.log(err);
    }
  }, [id]);

  useEffect(() => {
    fetchMember();
  }, [fetchMember]);

  const deleteMember = async () => {
    const confirmed = window.confirm(
      "Are you sure you want to delete this member?\n\nThis action cannot be undone."
    );

    if (!confirmed) return;

    try {
      await api.delete(`members/${member.id}/`);
      alert("Member deleted successfully.");
      navigate("/admin/members");
    } catch (err) {
      console.log(err);
      alert("Unable to delete member.");
    }
  };

  return (
    <Layout>
      {() => (
        <>
          {!member ? (
            <p>Loading member...</p>
          ) : (
            <>
              <h2 className="section-title">Member Profile</h2>

              <table className="table">
                <tbody>
                  <tr>
                    <th>Member Number</th>
                    <td>{member.member_number}</td>
                  </tr>
                  <tr>
                    <th>Full Name</th>
                    <td>{member.full_name}</td>
                  </tr>
                  <tr>
                    <th>Username</th>
                    <td>{member.username}</td>
                  </tr>
                  <tr>
                    <th>Email</th>
                    <td>{member.email}</td>
                  </tr>
                  <tr>
                    <th>National ID</th>
                    <td>{member.national_id}</td>
                  </tr>
                  <tr>
                    <th>Phone Number</th>
                    <td>{member.phone_number}</td>
                  </tr>
                  <tr>
                    <th>Gender</th>
                    <td>{member.gender}</td>
                  </tr>
                  <tr>
                    <th>Date of Birth</th>
                    <td>{member.date_of_birth}</td>
                  </tr>
                  <tr>
                    <th>County</th>
                    <td>{member.county}</td>
                  </tr>
                  <tr>
                    <th>Address</th>
                    <td>{member.address}</td>
                  </tr>
                  <tr>
                    <th>Status</th>
                    <td>{member.status}</td>
                  </tr>
                  <tr>
                    <th>Date Joined</th>
                    <td>{member.date_joined}</td>
                  </tr>
                </tbody>
              </table>

              <br />

              <h2 className="section-title">Financial Summary</h2>

              <div className="summary-grid">
                <div className="summary-card">
                  <h4>💰 Total Savings</h4>
                  <h2>KES {Number(member.total_savings).toLocaleString()}</h2>
                  <p>Current savings balance</p>
                </div>

                <div className="summary-card">
                  <h4>🏦 Total Loans</h4>
                  <h2>{member.total_loans}</h2>
                  <p>Loans applied</p>
                </div>

                <div className="summary-card">
                  <h4>⏳ Pending Loans</h4>
                  <h2>{member.pending_loans}</h2>
                  <p>Awaiting approval</p>
                </div>

                <div className="summary-card">
                  <h4>✅ Approved Loans</h4>
                  <h2>{member.approved_loans}</h2>
                  <p>Approved loans</p>
                </div>

                <div className="summary-card">
                  <h4>❌ Rejected Loans</h4>
                  <h2>{member.rejected_loans}</h2>
                  <p>Rejected applications</p>
                </div>

                <div className="summary-card">
                  <h4>💳 Transactions</h4>
                  <h2>{member.transactions}</h2>
                  <p>Total account transactions</p>
                </div>
              </div>

              <br />

              <button
                className="action-button"
                onClick={() => setShowEditModal(true)}
              >
                ✏️ Edit Member
              </button>

              <button
                className="action-button"
                onClick={deleteMember}
                style={{
                  marginLeft: "10px",
                  backgroundColor: "#dc3545",
                  color: "#fff",
                }}
              >
                🗑️ Delete Member
              </button>

              {showEditModal && (
                <EditMemberModal
                  member={member}
                  onClose={() => setShowEditModal(false)}
                  onUpdated={fetchMember}
                />
              )}
            </>
          )}
        </>
      )}
    </Layout>
  );
}

export default MemberProfile;
