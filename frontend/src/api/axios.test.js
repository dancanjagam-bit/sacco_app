// Regression tests for the SPA ↔ Django API base URL.
//
// Background: this app serves the React SPA and the Django API from the same
// Render web service, so the Axios client should use the same-origin relative
// base "/api/". A previous production build baked the placeholder
// https://your-backend.onrender.com/api/ into the bundle (via
// frontend/.env.production), so login posted to a non-existent host and
// failed with a 404 ("Something went wrong. Please try again."). These tests
// keep that from recurring.

const fs = require("fs");
const path = require("path");

function parseEnvFile(relativeToProjectRoot) {
  // __dirname is frontend/src/api; two levels up is the frontend project root.
  const filepath = path.join(__dirname, "..", "..", relativeToProjectRoot);
  if (!fs.existsSync(filepath)) return {};
  const out = {};
  for (const raw of fs.readFileSync(filepath, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const idx = line.indexOf("=");
    out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return out;
}

describe("API base URL configuration (src/api/axios.js)", () => {
  test("defaults to the same-origin relative /api/ base when REACT_APP_API_URL is unset", () => {
    jest.resetModules();
    // eslint-disable-next-line global-require
    const { authApi } = require("./axios");
    expect(authApi.defaults.baseURL).toBe("/api/");
  });

  test("uses a configured absolute backend URL with a normalised trailing slash when provided", () => {
    jest.resetModules();
    const previous = process.env.REACT_APP_API_URL;
    process.env.REACT_APP_API_URL = "https://api.nwtcs.co.ke/api";
    try {
      // eslint-disable-next-line global-require
      const { authApi } = require("./axios");
      expect(authApi.defaults.baseURL).toBe("https://api.nwtcs.co.ke/api/");
    } finally {
      if (previous === undefined) delete process.env.REACT_APP_API_URL;
      else process.env.REACT_APP_API_URL = previous;
    }
  });
});

describe("frontend/.env.production", () => {
  test("never bakes a placeholder backend URL into the production build", () => {
    const env = parseEnvFile(".env.production");
    const url = env.REACT_APP_API_URL;

    // Same-origin deployment ⇒ REACT_APP_API_URL should be unset/empty so the
    // SPA uses the relative "/api/" base. If it is ever set, it must be a real
    // URL — never a placeholder host such as "your-backend.onrender.com".
    if (url !== undefined && url !== "") {
      expect(url).not.toMatch(/your-backend/i);
      expect(url).not.toMatch(/example\.(com|invalid)/i);
      expect(url.startsWith("https://") || url.startsWith("/")).toBe(true);
    }
  });
});
