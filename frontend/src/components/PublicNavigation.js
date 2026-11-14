import React from "react";
import { Link, NavLink } from "react-router-dom";
import SaccoLogo from "./SaccoLogo";
import "../styles/sidebar.css";

export default function PublicNavigation() {
  return <header className="app-navigation app-public-navigation">
    <Link className="app-brand" to="/" aria-label="Nairobi West Transport Cooperative home">
      <span className="app-brand-mark"><SaccoLogo size={31} variant="light" /></span>
      <span className="app-brand-copy"><strong>Nairobi West</strong><small>Transport Cooperative</small></span>
    </Link>
    <nav className="app-primary-links" aria-label="Account access">
      <NavLink className={({ isActive }) => "app-nav-link" + (isActive ? " active" : "")} to="/" end>Sign in</NavLink>
      <NavLink className={({ isActive }) => "app-nav-link" + (isActive ? " active" : "")} to="/register">Register</NavLink>
    </nav>
  </header>;
}
