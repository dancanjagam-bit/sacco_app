import React, { createContext, useContext, useEffect, useState } from "react";
import { authApi } from "../api/axios";

const SaccoContext = createContext({
  name:       "Nairobi West Transport Cooperative Society",
  short_name: "NW Transport",
  address:    "Nairobi West, Nairobi County, Kenya",
  phone:      "0758007127",
  email:      "info@nwtcs.co.ke",
  paybill:    "174379",
});

export function SaccoProvider({ children }) {
  const [config, setConfig] = useState(null);

  useEffect(() => {
    authApi.get("config/")
      .then(r => setConfig(r.data))
      .catch(() => {}); // fall back to defaults above
  }, []);

  return (
    <SaccoContext.Provider value={config || SaccoContext._currentValue}>
      {children}
    </SaccoContext.Provider>
  );
}

export function useSacco() {
  return useContext(SaccoContext);
}
