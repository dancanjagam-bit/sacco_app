import React, { useEffect, useState } from "react";
import api from "../api/axios";

function EditMemberModal({
  member,
  onClose,
  onUpdated,
}) {
  const [formData, setFormData] = useState({
    phone_number: "",
    county: "",
    address: "",
    status: "",
  });

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (member) {
      setFormData({
        phone_number: member.phone_number,
        county: member.county,
        address: member.address,
        status: member.status,
      });
    }
  }, [member]);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const saveMember = async () => {
    setSaving(true);

    try {
      await api.put(
        `members/${member.id}/`,
        formData
      );

      alert("Member updated successfully.");

      onUpdated();
      onClose();
    } catch (err) {
      alert("Unable to update member.");
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
          width: 450,
        }}
      >
        <h2>Edit Member</h2>

        <br />

        <label>Phone Number</label>

        <input
          name="phone_number"
          value={formData.phone_number}
          onChange={handleChange}
          style={{ width: "100%" }}
        />

        <br />
        <br />

        <label>County</label>

        <input
          name="county"
          value={formData.county}
          onChange={handleChange}
          style={{ width: "100%" }}
        />

        <br />
        <br />

        <label>Address</label>

        <textarea
          name="address"
          value={formData.address}
          onChange={handleChange}
          style={{ width: "100%" }}
        />

        <br />
        <br />

        <label>Status</label>

        <select
          name="status"
          value={formData.status}
          onChange={handleChange}
          style={{ width: "100%" }}
        >
          <option value="active">
            Active
          </option>

          <option value="inactive">
            Inactive
          </option>

          <option value="suspended">
            Suspended
          </option>
        </select>

        <br />
        <br />

        <button
          onClick={saveMember}
          disabled={saving}
        >
          {saving ? "Saving..." : "Save Changes"}
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

export default EditMemberModal;
