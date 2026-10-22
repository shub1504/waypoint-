
import { useState } from "react";
import { post } from "../api.js";
import { useUI } from "../ui.js";

function Choice({ label, value, options, onChange, disabled = false }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          type="button"
          key={o}
          role="radio"
          aria-checked={value === o}
          className={value === o ? "on" : ""}
          disabled={disabled}
          onClick={() => onChange(o)}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

export default function AddAccount() {
  const ui = useUI();

  const [f, setF] = useState({
    name: "",
    email: "",
    phone: "",
    home_city: "Delhi",
    budget_level: "medium",
    alert_channel: "Push",
  });

  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [verifiedEmail, setVerifiedEmail] = useState("");
  const [otpBusy, setOtpBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("info");

  const email = f.email.trim().toLowerCase();
  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const verified = Boolean(verifiedEmail && verifiedEmail === email);

  const set = (key) => (e) => {
    const value = e.target.value;

    setF((current) => ({ ...current, [key]: value }));

    if (key === "email") {
      setOtp("");
      setOtpSent(false);
      setVerifiedEmail("");
      setMessage("");
    }
  };

  const requestOTP = async () => {
    if (!emailValid || otpBusy || verified) return;

    setOtpBusy(true);
    setMessage("");

    try {
      const response = await fetch("/api/auth/request-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data.detail || data.message || "Unable to generate OTP."
        );
      }

      setOtpSent(true);
      setOtp("");
      setVerifiedEmail("");
      setMessage(
        "OTP generated! Check the backend terminal for your testing code."
      );
      setMessageType("info");
    } catch (err) {
      setMessage(err.message || "Unable to request OTP.");
      setMessageType("error");
    } finally {
      setOtpBusy(false);
    }
  };

  const verifyOTP = async () => {
    if (!emailValid || !/^\d{6}$/.test(otp) || otpBusy) return;

    setOtpBusy(true);
    setMessage("");

    try {
      const response = await fetch("/api/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok || data.verified !== true) {
        throw new Error(
          data.detail || data.message || "Invalid or expired OTP."
        );
      }

      setVerifiedEmail(email);
      setMessage("Email verified successfully!");
      setMessageType("success");
    } catch (err) {
      setMessage(err.message || "OTP verification failed.");
      setMessageType("error");
    } finally {
      setOtpBusy(false);
    }
  };

  const ok = Boolean(
    verified &&
    f.name.trim() &&
    emailValid
  );

  const submit = async (e) => {
    e.preventDefault();

    // OTP verification is required before account creation.
    if (!verified || !ok || busy) return;

    setBusy(true);

    try {
      const m = await post("/api/members", {
        ...f,
        email,
      });

      ui.setMembers((members) =>
        members.some((member) => member.id === m.id)
          ? members
          : [...members, m]
      );

      ui.setMemberId(m.id);
      ui.closeSheet();
      ui.go("home");

      ui.toast(
        `Welcome, ${m.name.split(" ")[0]}! Your starter trip is ready. Try a disruption from Demo controls.`
      );
    } catch (err) {
      ui.toast(err.message || "Unable to create account.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="addform" onSubmit={submit}>
      <h3>Verify your email</h3>

      <label>
        Email
        <input
          className="text"
          type="email"
          value={f.email}
          onChange={set("email")}
          placeholder="you@example.com"
          autoComplete="email"
          required
        />
      </label>

      <button
        className="btn primary"
        type="button"
        onClick={requestOTP}
        disabled={!emailValid || otpBusy || verified}
      >
        {verified
          ? "Email verified ✓"
          : otpBusy
            ? "Please wait..."
            : otpSent
              ? "Resend OTP"
              : "Send OTP"}
      </button>

      {otpSent && !verified && (
        <>
          <label>
            Enter 6-digit OTP
            <input
              className="text"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={otp}
              onChange={(e) =>
                setOtp(
                  e.target.value.replace(/\D/g, "").slice(0, 6)
                )
              }
              placeholder="Enter OTP"
              required
            />
          </label>

          <button
            className="btn primary"
            type="button"
            onClick={verifyOTP}
            disabled={!/^\d{6}$/.test(otp) || otpBusy}
          >
            {otpBusy ? "Verifying..." : "Verify OTP"}
          </button>
        </>
      )}

      {message && (
        <p
          className="sub"
          role="status"
          aria-live="polite"
          style={{
            color:
              messageType === "error"
                ? "#c62828"
                : messageType === "success"
                  ? "#23834b"
                  : undefined,
          }}
        >
          {message}
        </p>
      )}

      <fieldset
        disabled={!verified || busy}
        style={{
          border: 0,
          padding: 0,
          margin: "16px 0 0",
          minWidth: 0,
          opacity: verified ? 1 : 0.5,
        }}
      >
        <legend style={{ marginBottom: 12, fontWeight: 600 }}>
          Account details
        </legend>

        <label>
          Full name
          <input
            className="text"
            value={f.name}
            onChange={set("name")}
            autoComplete="name"
            required
          />
        </label>

        <label>
          Phone
          <input
            className="text"
            type="tel"
            value={f.phone}
            onChange={set("phone")}
            autoComplete="tel"
          />
        </label>

        <label>
          Home city
          <input
            className="text"
            value={f.home_city}
            onChange={set("home_city")}
          />
        </label>

        <div>
          <span className="lab">Budget comfort</span>
          <Choice
            label="Budget comfort"
            value={f.budget_level}
            options={["low", "medium", "high"]}
            disabled={!verified || busy}
            onChange={(value) =>
              setF((current) => ({
                ...current,
                budget_level: value,
              }))
            }
          />
        </div>

        <div>
          <span className="lab">Alert me by</span>
          <Choice
            label="Alert channel"
            value={f.alert_channel}
            options={["Push", "SMS", "Email"]}
            disabled={!verified || busy}
            onChange={(value) =>
              setF((current) => ({
                ...current,
                alert_channel: value,
              }))
            }
          />
        </div>

        <p className="sub">
          You get a starter trip (flight, hotel, train) and past
          temple stays, so you can try disruption scenarios on
          this account.
        </p>

        <button
          className="btn primary"
          type="submit"
          disabled={!ok || busy}
        >
          {busy ? "Creating account..." : "Create account"}
        </button>
      </fieldset>
    </form>
  );
}
