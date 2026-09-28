"use client";
import { useEffect, useState } from "react";
import { ENTERPRISE_PERSONAS, getSession, login, switchPersona, type EnterprisePersona } from "../lib/auth";

export type SignInModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

export default function SignInModal({ isOpen, onClose }: SignInModalProps) {
  const [tab, setTab] = useState<"personas" | "custom">("personas");
  const [customName, setCustomName] = useState("");
  const [customEmail, setCustomEmail] = useState("");
  const [customTenant, setCustomTenant] = useState("vantor-corp");
  const [customRole, setCustomRole] = useState("Procurement Manager");
  const currentSession = getSession();

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSelectPersona = (p: EnterprisePersona) => {
    switchPersona(p.id);
    onClose();
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    login(undefined, {
      name: customName.trim() || customEmail.split("@")[0] || "Enterprise Executive",
      tenant: customTenant.trim() || "vantor-corp",
      roles: [customRole, "Buyer"],
    });
    onClose();
  };

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="signin-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-container">
        <div className="modal-header">
          <div>
            <div className="modal-eyebrow">VANTOR ENTERPRISE ACCESS</div>
            <h2 id="signin-modal-title" className="modal-title">Sign In & Role Delegation</h2>
            <p className="modal-sub">
              Authenticate into Vantor Procurement OS with an authorized executive persona or enterprise credentials.
            </p>
          </div>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Close sign-in modal"
          >
            ✕
          </button>
        </div>

        <div className="modal-tabs">
          <button
            type="button"
            className={`modal-tab ${tab === "personas" ? "active" : ""}`}
            onClick={() => setTab("personas")}
          >
            Certified Executive Personas
          </button>
          <button
            type="button"
            className={`modal-tab ${tab === "custom" ? "active" : ""}`}
            onClick={() => setTab("custom")}
          >
            Custom Enterprise Identity
          </button>
        </div>

        <div className="modal-body">
          {tab === "personas" ? (
            <div className="personas-list">
              {ENTERPRISE_PERSONAS.map((p) => {
                const isActive = currentSession?.name === p.name;
                return (
                  <div
                    key={p.id}
                    className={`persona-card ${isActive ? "persona-card-active" : ""}`}
                    onClick={() => handleSelectPersona(p)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleSelectPersona(p);
                      }
                    }}
                  >
                    <div className="persona-header">
                      <div className="persona-info">
                        <div className="persona-name">
                          {p.name}
                          {isActive ? <span className="persona-active-badge">Active</span> : null}
                        </div>
                        <div className="persona-title">{p.title}</div>
                      </div>
                      <button
                        type="button"
                        className={`persona-select-btn ${isActive ? "btn-active" : ""}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSelectPersona(p);
                        }}
                      >
                        {isActive ? "Current Role" : "Select Role"}
                      </button>
                    </div>
                    <div className="persona-desc">{p.description}</div>
                    <div className="persona-meta">
                      <span className="persona-email">{p.email}</span>
                      <span className="persona-tenant">tenant: {p.tenant}</span>
                      <div className="persona-roles">
                        {p.roles.map((r) => (
                          <span key={r} className="persona-role-pill">{r}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <form onSubmit={handleCustomSubmit} className="custom-login-form">
              <label>
                <span>Full Name</span>
                <input
                  type="text"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="e.g. Jordan Hayes"
                />
              </label>

              <label>
                <span>Corporate Email</span>
                <input
                  type="email"
                  value={customEmail}
                  onChange={(e) => setCustomEmail(e.target.value)}
                  placeholder="jordan.hayes@vantor-enterprise.com"
                />
              </label>

              <label>
                <span>Tenant Domain</span>
                <input
                  type="text"
                  value={customTenant}
                  onChange={(e) => setCustomTenant(e.target.value)}
                  placeholder="vantor-corp"
                />
              </label>

              <label>
                <span>Primary Delegation Role</span>
                <select
                  value={customRole}
                  onChange={(e) => setCustomRole(e.target.value)}
                >
                  <option value="Procurement Manager">Procurement Manager (Approval Authority)</option>
                  <option value="Category Manager">Category Manager (Strategic Sourcing & RFQs)</option>
                  <option value="Finance Reviewer">Finance Reviewer (3-Way Matching & Invoices)</option>
                  <option value="Buyer">Senior Buyer (Requisitions & POs)</option>
                  <option value="Admin">System Administrator</option>
                </select>
              </label>

              <div className="custom-form-actions">
                <button type="submit" className="custom-submit-btn">
                  Sign In to Enterprise Workspace
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
