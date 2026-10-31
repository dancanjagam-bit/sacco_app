import React, { useState, useRef, useCallback } from "react";
import Webcam from "react-webcam";

function dataURLtoFile(dataURL, filename) {
  const arr = dataURL.split(",");
  const mime = arr[0].match(/:(.*?);/)[1];
  const bstr = atob(arr[1]);
  let n = bstr.length;
  const u8arr = new Uint8Array(n);
  while (n--) u8arr[n] = bstr.charCodeAt(n);
  return new File([u8arr], filename, { type: mime });
}

function SelfieCapture({ onChange, disabled = false }) {
  const [mode, setMode] = useState("webcam");
  const [captured, setCaptured] = useState(null);
  const [cameraError, setCameraError] = useState(false);
  const webcamRef = useRef(null);

  const handleCapture = useCallback(() => {
    if (!webcamRef.current) return;
    const imageSrc = webcamRef.current.getScreenshot();
    if (!imageSrc) return;
    setCaptured(imageSrc);
    if (onChange) onChange(dataURLtoFile(imageSrc, "selfie.jpg"));
  }, [onChange]);

  const handleCameraError = useCallback(() => {
    setCameraError(true);
    setMode("upload");
  }, []);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file && onChange) onChange(file);
  };

  if (mode === "upload" || cameraError) {
    return (
      <div className="selfie-capture">
        <label htmlFor="selfie-upload-input" className="form-label fw-semibold">
          Selfie Photo <span className="text-muted small">(JPEG, PNG, or GIF)</span>
        </label>
        {cameraError && (
          <p className="text-muted small mb-1">Camera access was denied — please upload a selfie photo instead.</p>
        )}
        <input
          id="selfie-upload-input"
          type="file"
          accept="image/jpeg,image/png,image/gif"
          onChange={handleFileChange}
          disabled={disabled}
          className="form-control"
          aria-label="Upload a selfie photo"
        />
        {!cameraError && (
          <button type="button" className="btn btn-sm btn-outline-secondary mt-2"
            onClick={() => setMode("webcam")}>
            Use camera instead
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="selfie-capture">
      <p className="form-label fw-semibold mb-1">
        Selfie Photo <span className="text-muted small">(take a photo or upload)</span>
      </p>
      {captured ? (
        <div>
          <img src={captured} alt="Captured selfie"
            style={{ maxWidth: "100%", maxHeight: "200px", borderRadius: "6px", border: "1px solid #dee2e6" }} />
          <div className="mt-2">
            <button type="button" className="btn btn-sm btn-outline-danger"
              onClick={() => { setCaptured(null); if (onChange) onChange(null); }}
              aria-label="Retake selfie photo">Retake</button>
          </div>
        </div>
      ) : (
        <div>
          <Webcam ref={webcamRef} screenshotFormat="image/jpeg" width="100%"
            style={{ maxWidth: "320px", borderRadius: "6px" }}
            onUserMediaError={handleCameraError} />
          <div className="mt-2 d-flex gap-2 flex-wrap">
            <button type="button" className="btn btn-sm btn-primary"
              onClick={handleCapture} disabled={disabled} aria-label="Take selfie photo">
              📸 Take Photo
            </button>
            <button type="button" className="btn btn-sm btn-outline-secondary"
              onClick={() => setMode("upload")}>Upload instead</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default SelfieCapture;
