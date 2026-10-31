import React, { useState, useRef, useCallback, useEffect } from "react";
import Webcam from "react-webcam";

/**
 * Convert a base64 data-URL to a File object.
 */
function dataURLtoFile(dataURL, filename) {
  const arr  = dataURL.split(",");
  const mime = arr[0].match(/:(.*?);/)[1];
  const bstr = atob(arr[1]);
  let n = bstr.length;
  const u8arr = new Uint8Array(n);
  while (n--) u8arr[n] = bstr.charCodeAt(n);
  return new File([u8arr], filename, { type: mime });
}

/**
 * SelfieCapture
 * ─────────────
 * Works on all devices — desktop laptops, phones, tablets.
 * - Tries webcam first (works on Chrome, Firefox, Edge, Safari over HTTPS or localhost)
 * - Falls back to file upload if camera permission is denied or unavailable
 * - "Take Photo" button is disabled until the webcam stream is fully ready
 * - Shows a green indicator when camera is live
 */
export default function SelfieCapture({ onChange, disabled = false }) {
  const [mode,         setMode]         = useState("webcam");
  const [captured,     setCaptured]     = useState(null);
  const [cameraError,  setCameraError]  = useState(false);
  const [cameraReady,  setCameraReady]  = useState(false);  // true once stream is live
  const [previewFile,  setPreviewFile]  = useState(null);   // upload preview URL
  const webcamRef = useRef(null);

  // Clean up preview object-URL on unmount
  useEffect(() => {
    return () => { if (previewFile) URL.revokeObjectURL(previewFile); };
  }, [previewFile]);

  const handleUserMedia = useCallback(() => {
    // Called by react-webcam when the camera stream starts successfully
    setCameraReady(true);
    setCameraError(false);
  }, []);

  const handleCameraError = useCallback((err) => {
    // NotAllowedError = permission denied; NotFoundError = no camera
    console.warn("Camera unavailable:", err);
    setCameraError(true);
    setCameraReady(false);
    setMode("upload");
  }, []);

  const handleCapture = useCallback(() => {
    if (!webcamRef.current || !cameraReady) return;
    const imageSrc = webcamRef.current.getScreenshot();
    if (!imageSrc) {
      alert("Camera not ready yet. Please wait a moment and try again.");
      return;
    }
    setCaptured(imageSrc);
    const file = dataURLtoFile(imageSrc, "selfie.jpg");
    if (onChange) onChange(file);
  }, [onChange, cameraReady]);

  const handleRetake = useCallback(() => {
    setCaptured(null);
    setCameraReady(false);
    if (onChange) onChange(null);
  }, [onChange]);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (previewFile) URL.revokeObjectURL(previewFile);
    setPreviewFile(URL.createObjectURL(file));
    if (onChange) onChange(file);
  };

  // ── Video constraints: prefer front camera, explicit resolution ──────
  const videoConstraints = {
    width:      { ideal: 640 },
    height:     { ideal: 480 },
    facingMode: "user",   // front camera on phones; built-in on laptops
  };

  // ── Upload fallback (camera denied or user chose to upload) ───────────
  if (mode === "upload" || cameraError) {
    return (
      <div style={{ marginTop: "8px" }}>
        <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "#475569", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: "6px" }}>
          Selfie Photo
          <span style={{ color: "#94a3b8", fontWeight: "400", textTransform: "none", marginLeft: "6px" }}>
            (JPEG, PNG, or GIF)
          </span>
        </label>

        {cameraError && (
          <div style={{ padding: "10px 14px", background: "#fef3c7", borderRadius: "8px", fontSize: "12px", color: "#92400e", marginBottom: "10px", border: "1px solid #fcd34d" }}>
            📷 Camera access was denied or not available. Upload a photo instead.
          </div>
        )}

        {/* Preview */}
        {previewFile && (
          <div style={{ marginBottom: "10px" }}>
            <img src={previewFile} alt="Selfie preview"
              style={{ maxWidth: "200px", maxHeight: "200px", borderRadius: "8px", border: "2px solid #2563eb", display: "block" }} />
          </div>
        )}

        <input
          id="selfie-upload"
          type="file"
          accept="image/jpeg,image/png,image/gif"
          onChange={handleFileChange}
          disabled={disabled}
          style={{ display: "block", fontSize: "14px" }}
          aria-label="Upload a selfie photo"
        />

        {!cameraError && (
          <button type="button"
            onClick={() => { setMode("webcam"); setCameraError(false); setCameraReady(false); }}
            style={{ marginTop: "10px", padding: "6px 14px", background: "none", border: "1.5px solid #e2e8f0", borderRadius: "8px", fontSize: "12px", fontWeight: "600", cursor: "pointer", color: "#475569" }}>
            📷 Try camera instead
          </button>
        )}
      </div>
    );
  }

  // ── Webcam mode ────────────────────────────────────────────────────────
  return (
    <div style={{ marginTop: "8px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
        <label style={{ fontSize: "12px", fontWeight: "700", color: "#475569", textTransform: "uppercase", letterSpacing: ".5px" }}>
          Selfie Photo
        </label>
        {cameraReady && !captured && (
          <span style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "11px", color: "#16a34a", fontWeight: "600" }}>
            <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#16a34a", display: "inline-block", animation: "pulse 1.5s infinite" }} />
            Camera live
          </span>
        )}
        {!cameraReady && !captured && (
          <span style={{ fontSize: "11px", color: "#94a3b8" }}>Starting camera...</span>
        )}
      </div>

      {captured ? (
        // ── Show the captured photo ──
        <div>
          <img src={captured} alt="Your selfie"
            style={{ maxWidth: "220px", maxHeight: "220px", borderRadius: "10px", border: "2px solid #2563eb", display: "block", marginBottom: "10px" }} />
          <div style={{ display: "flex", gap: "8px" }}>
            <button type="button" onClick={handleRetake} disabled={disabled}
              style={{ padding: "7px 16px", background: "#fee2e2", color: "#b91c1c", border: "none", borderRadius: "8px", fontSize: "13px", fontWeight: "600", cursor: "pointer" }}>
              🔄 Retake
            </button>
          </div>
        </div>
      ) : (
        // ── Live webcam feed ──
        <div>
          <div style={{ position: "relative", display: "inline-block", maxWidth: "100%" }}>
            <Webcam
              ref={webcamRef}
              audio={false}
              screenshotFormat="image/jpeg"
              videoConstraints={videoConstraints}
              onUserMedia={handleUserMedia}
              onUserMediaError={handleCameraError}
              style={{ maxWidth: "320px", width: "100%", borderRadius: "10px", border: "2px solid #e2e8f0", display: "block" }}
              mirrored={true}
            />
            {/* Overlay guide */}
            {cameraReady && (
              <div style={{
                position: "absolute", top: "50%", left: "50%",
                transform: "translate(-50%, -50%)",
                width: "140px", height: "170px",
                border: "2px dashed rgba(37,99,235,.5)",
                borderRadius: "50%",
                pointerEvents: "none",
              }} />
            )}
          </div>

          <div style={{ display: "flex", gap: "8px", marginTop: "10px", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={handleCapture}
              disabled={disabled || !cameraReady}
              style={{
                padding: "10px 20px",
                background: cameraReady ? "#2563eb" : "#e2e8f0",
                color: cameraReady ? "#fff" : "#94a3b8",
                border: "none", borderRadius: "8px",
                fontSize: "14px", fontWeight: "700",
                cursor: cameraReady ? "pointer" : "not-allowed",
                transition: "all .2s",
              }}
              aria-label="Take selfie photo"
            >
              📸 {cameraReady ? "Take Photo" : "Waiting for camera..."}
            </button>

            <button type="button"
              onClick={() => setMode("upload")}
              style={{ padding: "10px 16px", background: "#f8fafc", border: "1.5px solid #e2e8f0", borderRadius: "8px", fontSize: "13px", fontWeight: "600", cursor: "pointer", color: "#475569" }}>
              📁 Upload instead
            </button>
          </div>
        </div>
      )}

      {/* Helpful note */}
      <p style={{ fontSize: "11px", color: "#94a3b8", marginTop: "8px" }}>
        Position your face within the oval guide and click Take Photo.
        Camera works on laptops and phones over HTTPS or localhost.
      </p>
    </div>
  );
}
