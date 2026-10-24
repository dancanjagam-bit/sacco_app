import axios from "axios";

const api = axios.create({
  baseURL: "http://127.0.0.1:8000/api/",
});

// ── Request interceptor: attach access token ──────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access");

  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

// ── Response interceptor: auto-refresh on 401 ─────────────────────────────
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

    // Only attempt refresh on 401 and only once per request
    if (
      error.response?.status === 401 &&
      !originalRequest._retry
    ) {
      const refreshToken = localStorage.getItem("refresh");

      // No refresh token — force logout
      if (!refreshToken) {
        localStorage.clear();
        window.location.href = "/";
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Queue concurrent requests while a refresh is in-flight
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
          "http://127.0.0.1:8000/api/token/refresh/",
          { refresh: refreshToken }
        );

        const newAccess = res.data.access;
        localStorage.setItem("access", newAccess);

        api.defaults.headers.common.Authorization = `Bearer ${newAccess}`;
        originalRequest.headers.Authorization = `Bearer ${newAccess}`;

        processQueue(null, newAccess);
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        localStorage.clear();
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
