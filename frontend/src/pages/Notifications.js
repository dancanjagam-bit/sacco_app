import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import api from "../api/axios";
import Button from "../components/ui/Button";
import FeedbackMessage from "../components/ui/FeedbackMessage";
import Icon from "../components/ui/Icon";
import LoadingState from "../components/ui/LoadingState";
import PageHeading from "../components/ui/PageHeading";
import "../styles/member-notifications.css";

const typeLabel = {
  success: "Update",
  info: "Information",
  warning: "Action needed",
  error: "Issue",
};

export default function Notifications() {
  const [items, setItems] = useState(null);
  const [notices, setNotices] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [updating, setUpdating] = useState(false);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const response = await api.get("notifications/");
      const notifications = response?.data?.notifications;
      if (!Array.isArray(notifications)) {
        throw new Error("Invalid notifications response");
      }
      const count = Number(response.data.unread_count);
      setItems(notifications);
      setNotices(Array.isArray(response.data.member_notices) ? response.data.member_notices : []);
      setUnread(Number.isFinite(count) && count >= 0
        ? count
        : notifications.filter((item) => !item.is_read).length);
    } catch {
      setItems(null);
      setNotices([]);
      setUnread(0);
      setLoadError("Could not load notifications. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchNotifications(); }, [fetchNotifications]);

  const markRead = async (id) => {
    setUpdating(true);
    setActionError("");
    try {
      await api.post(`notifications/${id}/read/`);
      setItems((current) => current?.map((item) =>
        item.id === id ? { ...item, is_read: true } : item
      ) ?? null);
      setUnread((current) => Math.max(0, current - 1));
    } catch {
      setActionError("We could not update this notification. Please retry.");
    } finally {
      setUpdating(false);
    }
  };

  const markAllRead = async () => {
    setUpdating(true);
    setActionError("");
    try {
      await api.post("notifications/read-all/");
      setItems((current) => current?.map((item) => ({ ...item, is_read: true })) ?? null);
      setUnread(0);
    } catch {
      setActionError("We could not update your notifications. Please retry.");
    } finally {
      setUpdating(false);
    }
  };

  return (
    <Layout>
      <PageHeading
        eyebrow="Account updates"
        title="Notifications"
        description="Updates about your account activity and requests."
        actions={items?.length > 0 && unread > 0 ? (
          <Button variant="secondary" onClick={markAllRead} loading={updating}>
            Mark all as read
          </Button>
        ) : null}
      />

      {!loading && notices.length > 0 && (
        <section className="member-notifications-list" aria-label="Cooperative notices">
          <h2>Cooperative notices</h2>
          {notices.map((notice) => (
            <article className="member-notification member-notification-info" key={notice.id}>
              <div className="member-notification-content">
                <span className="member-notification-kind">{notice.priority === "urgent" ? "Urgent notice" : "Notice"}</span>
                <h3>{notice.title}</h3>
                <p style={{ whiteSpace: "pre-wrap" }}>{notice.body}</p>
              </div>
            </article>
          ))}
        </section>
      )}

      {loading ? <LoadingState label="Loading notifications…" /> : loadError ? (
        <FeedbackMessage
          tone="danger"
          title="Notifications could not be loaded"
          action={<Button variant="secondary" onClick={fetchNotifications}>Retry</Button>}
        >
          {loadError}
        </FeedbackMessage>
      ) : items?.length === 0 && notices.length === 0 ? (
        <section className="member-notifications-empty" aria-live="polite">
          <Icon name="bell" size={22} />
          <h2>All caught up!</h2>
          <p>You’ll see updates about your account activity here.</p>
        </section>
      ) : (
        <section className="member-notifications-list" aria-label="Your notifications">
          <p className="member-notifications-summary" aria-live="polite">
            {unread > 0 ? `${unread} unread notification${unread === 1 ? "" : "s"}` : "No unread notifications."}
          </p>
          {actionError && <FeedbackMessage tone="danger" title="Update failed">{actionError}</FeedbackMessage>}
          {(items ?? []).map((item) => (
            <article className={`member-notification member-notification-${item.type || "info"}`} key={item.id}>
              <div className="member-notification-mark" aria-hidden="true"><Icon name={item.type === "warning" || item.type === "error" ? "alert" : item.type === "success" ? "check" : "bell"} size={18} /></div>
              <div className="member-notification-content">
                <div className="member-notification-heading">
                  <div>
                    <span className="member-notification-kind">{typeLabel[item.type] || "Notification"}</span>
                    <h2>{item.title}</h2>
                  </div>
                  <time dateTime={item.created_at}>
                    {item.created_at ? new Date(item.created_at).toLocaleString("en-KE", { dateStyle: "medium", timeStyle: "short" }) : ""}
                  </time>
                </div>
                <p>{item.message}</p>
                <div className="member-notification-actions">
                  {!item.is_read && <Button size="sm" variant="secondary" disabled={updating} onClick={() => markRead(item.id)}>Mark as read</Button>}
                  {item.link && <Button as={Link} size="sm" variant="ghost" to={item.link}>View update</Button>}
                  <span className="member-notification-state">{item.is_read ? "Read" : "Unread"}</span>
                </div>
              </div>
            </article>
          ))}
        </section>
      )}
    </Layout>
  );
}
