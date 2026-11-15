import React, { useEffect, useState } from "react";
import api from "../api/axios";
import Button from "./ui/Button";
import FeedbackMessage from "./ui/FeedbackMessage";
import FormField from "./ui/FormField";
import Icon from "./ui/Icon";

const PHOTO_ENDPOINT = "profile/photo/";
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

export default function ProfilePhoto({ hasPhoto: initialHasPhoto }) {
  const [hasPhoto, setHasPhoto] = useState(initialHasPhoto);
  const [revision, setRevision] = useState(0);
  const [url, setUrl] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!hasPhoto) return undefined;
    let objectUrl;
    const controller = new AbortController();
    api.get(PHOTO_ENDPOINT, { responseType: "blob", signal: controller.signal })
      .then(({ data }) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(data);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setUrl("");
          setMessage({ tone: "warning", text: "Your saved photo could not be loaded." });
        }
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [hasPhoto, revision]);

  async function upload(event) {
    event.preventDefault();
    if (!file || busy) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setMessage({ tone: "danger", text: "Choose an image no larger than 5 MB." });
      return;
    }

    const form = event.currentTarget;
    const data = new FormData();
    data.append("photo", file);
    setBusy(true);
    setMessage(null);
    try {
      await api.post(PHOTO_ENDPOINT, data);
      setUrl("");
      setHasPhoto(true);
      setRevision((current) => current + 1);
      form.reset();
      setFile(null);
      setMessage({ tone: "success", text: "Profile photo saved." });
    } catch (error) {
      setMessage({ tone: "danger", text: error.response?.data?.error || "Your photo could not be uploaded. Please try again." });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setMessage(null);
    try {
      await api.delete(PHOTO_ENDPOINT);
      setUrl("");
      setHasPhoto(false);
      setMessage({ tone: "success", text: "Profile photo removed." });
    } catch {
      setMessage({ tone: "danger", text: "Your photo could not be removed. Please try again." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="ui-panel member-profile-card" aria-labelledby="profile-photo-title">
      <div className="ui-panel-header"><h2 className="ui-panel-title" id="profile-photo-title">Profile photo</h2></div>
      <div className="ui-panel-body member-profile-photo">
        <div className="member-profile-photo-frame">
          {url ? <img src={url} alt="Your member portrait" /> : <Icon name="user" size={32} />}
        </div>
        {message && <FeedbackMessage tone={message.tone}>{message.text}</FeedbackMessage>}
        <form className="member-profile-form" onSubmit={upload}>
          <FormField label="Choose photo" htmlFor="member-photo" hint="JPEG, PNG, or WebP, up to 5 MB.">
            <input id="member-photo" className="ui-input" type="file" accept="image/jpeg,image/png,image/webp"
              disabled={busy} onChange={(event) => setFile(event.target.files[0] || null)} />
          </FormField>
          <div className="member-profile-actions">
            <Button type="submit" disabled={!file || busy}>Save photo</Button>
            {hasPhoto && <Button variant="secondary" disabled={busy} onClick={remove}>Remove photo</Button>}
          </div>
        </form>
      </div>
    </section>
  );
}
