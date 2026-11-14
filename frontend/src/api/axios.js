import axios from "axios";

const configuredApiUrl = process.env.REACT_APP_API_URL?.trim();
const apiBaseUrl = configuredApiUrl
  ? `${configuredApiUrl.replace(/\/+$/, "")}/`
  : "/api/";

const api = axios.create({ baseURL: apiBaseUrl });

// A separate plain instance for auth endpoints — no interceptors, no token injection
export const authApi = axios.create({ baseURL: apiBaseUrl });

function readToken(key) {
  return sessionStorage.getItem(key) || localStorage.getItem(key);
}

function writeToken(key, value) {
  localStorage.removeItem(key);
  sessionStorage.removeItem(key);
  if (value) {
    const storage = localStorage.getItem("sacco_remember_session") === "true" ? localStorage : sessionStorage;
    storage.setItem(key, value);
  }
}

// Request interceptor: attach access token
api.interceptors.request.use((config) => {
  const token = readToken("access");

  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  } else if (config.headers) {
    delete config.headers.Authorization;
  }

  return config;
});

// Response interceptor: auto-refresh on 401
let isRefreshing = false;
let failedQueue = [];

function processQueue(error, token = null) {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      !originalRequest._retry
    ) {
      const refreshToken = readToken("refresh");

      if (!refreshToken) {
        writeToken("access", null);
        writeToken("refresh", null);
        window.location.href = "/";
        return Promise.reject(error);
      }

      if (isRefreshing) {
        originalRequest._retry = true;
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return api(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const res = await axios.post(
          `${apiBaseUrl}token/refresh/`,
          { refresh: refreshToken }
        );

        const newAccess = res.data.access;
        writeToken("access", newAccess);
        if (res.data.refresh) writeToken("refresh", res.data.refresh);

        originalRequest.headers.Authorization = `Bearer ${newAccess}`;
        originalRequest._retry = true;

        processQueue(null, newAccess);
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        writeToken("access", null);
        writeToken("refresh", null);
        window.location.href = "/";
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
