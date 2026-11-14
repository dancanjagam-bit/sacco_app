function blobAsArrayBuffer(blob) {
  if (typeof blob.arrayBuffer === "function") return blob.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error("Unable to read report file."));
    reader.readAsArrayBuffer(blob);
  });
}

function blobAsText(blob) {
  if (typeof blob.text === "function") return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Unable to read report response."));
    reader.readAsText(blob);
  });
}

function responseFilename(disposition, fallback) {
  if (!disposition) return fallback;
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (encoded) {
    try { return decodeURIComponent(encoded[1].trim()); } catch { return fallback; }
  }
  const quoted = disposition.match(/filename="?([^";]+)"?/i);
  return quoted?.[1]?.trim() || fallback;
}

async function readableDownloadError(blob) {
  try {
    const text = await blobAsText(blob);
    const parsed = JSON.parse(text);
    return parsed.error || parsed.detail || parsed.message || "The server could not generate this report.";
  } catch {
    return "The server returned an invalid report. Please retry or contact support.";
  }
}

export async function downloadFailureMessage(error, fallback) {
  const payload = error?.response?.data;
  if (payload instanceof Blob) return readableDownloadError(payload);
  if (payload && typeof payload === "object") {
    return payload.error || payload.detail || payload.message || fallback;
  }
  return error?.message || fallback;
}

export async function downloadStatement(response, { format, fallbackFilename }) {
  const blob = response.data instanceof Blob
    ? response.data
    : new Blob([response.data], { type: response.headers?.["content-type"] || "" });
  const contentType = String(response.headers?.["content-type"] || blob.type || "").toLowerCase();

  if (format === "pdf") {
    const firstBytes = new Uint8Array(await blobAsArrayBuffer(blob.slice(0, 5)));
    const signature = String.fromCharCode(...firstBytes);
    if (!contentType.includes("application/pdf") || signature !== "%PDF-") {
      throw new Error(await readableDownloadError(blob));
    }
  } else if (format === "xlsx") {
    const signature = new Uint8Array(await blobAsArrayBuffer(blob.slice(0, 4)));
    const isZip = signature.length === 4 && signature[0] === 0x50 && signature[1] === 0x4b
      && signature[2] === 0x03 && signature[3] === 0x04;
    if (!contentType.includes("spreadsheetml") || !isZip) {
      throw new Error(await readableDownloadError(blob));
    }
  } else {
    throw new Error("Unsupported report format.");
  }

  const filename = responseFilename(response.headers?.["content-disposition"], fallbackFilename);
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
  return filename;
}
