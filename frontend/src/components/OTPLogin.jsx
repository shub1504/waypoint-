import { useState } from "react";

export default function OTPLogin({ onVerified }) {
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function sendOtp(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");

    try {
      const res = await fetch("/api/auth/request-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not send OTP");
      setSent(true);
      setMessage("OTP generated! Check your backend terminal.");
    } catch (err) {
      setError(err.message || "Cannot connect to backend. Is it running?");
    } finally {
      setBusy(false);
    }
  }

  async function verifyOtp(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");

    try {
      const res = await fetch("/api/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "OTP verification failed");
      onVerified();
    } catch (err) {
      setError(err.message || "Could not verify OTP");
    } finally {
      setBusy(false);
    }
  }

  const inputStyle = {
    width: "100%",
    boxSizing: "border-box",
    padding: "13px 14px",
    border: "1px solid #e9deeb",
    borderRadius: 12,
    fontSize: 15,
    outlineColor: "#d95f8b",
    background: "#fff",
    color: "#29344b",
  };

  const buttonStyle = {
    width: "100%",
    padding: 14,
    border: 0,
    borderRadius: 12,
    background: "#d95f8b",
    color: "#fff",
    fontWeight: 700,
    fontSize: 15,
    cursor: "pointer",
    marginTop: 8,
  };

  return (
    <main style={{
      minHeight: "100vh",
      display: "grid",
      placeItems: "center",
      padding: 20,
      boxSizing: "border-box",
      background: "linear-gradient(135deg, #fff5f8, #f8f6fb 55%, #f0f5ff)",
      fontFamily: "Inter, system-ui, sans-serif",
    }}>
      <section style={{
        width: "100%",
        maxWidth: 410,
        boxSizing: "border-box",
        padding: "34px 28px",
        borderRadius: 24,
        background: "#fff",
        border: "1px solid #f0e6ef",
        boxShadow: "0 20px 60px rgba(63, 44, 73, 0.09)",
      }}>
        <div style={{
          width: 54, height: 54, borderRadius: 17,
          display: "grid", placeItems: "center",
          background: "#fff0f5", fontSize: 27, marginBottom: 20,
        }}>✈️</div>

        <p style={{
          color: "#d95f8b", fontSize: 12, fontWeight: 800,
          letterSpacing: 2, margin: "0 0 10px",
        }}>WELCOME TO WAYPOINT</p>

        <h1 style={{
          fontSize: 29, lineHeight: 1.2, color: "#29344b",
          margin: "0 0 10px",
        }}>Your next journey starts here.</h1>

        <p style={{
          color: "#59677e", fontSize: 14, lineHeight: 1.6,
          margin: "0 0 25px",
        }}>Sign in with your email to continue to your travel dashboard.</p>

        {!sent ? (
          <form onSubmit={sendOtp}>
            <label htmlFor="wp-email" style={{
              display: "block", fontSize: 13, fontWeight: 700,
              color: "#29344b", marginBottom: 8,
            }}>Email address</label>
            <input
              id="wp-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              style={inputStyle}
            />
            <button type="submit" disabled={busy} style={{
              ...buttonStyle, opacity: busy ? 0.7 : 1,
            }}>{busy ? "Sending..." : "Send OTP →"}</button>
          </form>
        ) : (
          <form onSubmit={verifyOtp}>
            <p style={{
              fontSize: 13, color: "#59677e", lineHeight: 1.5,
              margin: "0 0 15px",
            }}>Enter the 6-digit testing code generated for <b>{email}</b>.</p>
            <label htmlFor="wp-otp" style={{
              display: "block", fontSize: 13, fontWeight: 700,
              color: "#29344b", marginBottom: 8,
            }}>Verification code</label>
            <input
              id="wp-otp"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              required
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="Enter 6-digit OTP"
              style={{ ...inputStyle, letterSpacing: 7, textAlign: "center", fontSize: 20 }}
            />
            <button type="submit" disabled={busy || otp.length !== 6} style={{
              ...buttonStyle, opacity: busy || otp.length !== 6 ? 0.7 : 1,
            }}>{busy ? "Verifying..." : "Verify OTP & Continue"}</button>
            <button type="button" onClick={() => {
              setSent(false);
              setOtp("");
              setError("");
              setMessage("");
            }} style={{
              width: "100%", marginTop: 12, padding: 10,
              border: 0, background: "transparent", color: "#59677e",
              cursor: "pointer",
            }}>← Change email</button>
          </form>
        )}

        {message && <p role="status" style={{
          color: "#28734b", background: "#edf9f1", padding: 11,
          borderRadius: 10, fontSize: 13, lineHeight: 1.5,
        }}>{message}</p>}

        {error && <p role="alert" style={{
          color: "#b42345", background: "#fff0f2", padding: 11,
          borderRadius: 10, fontSize: 13, lineHeight: 1.5,
        }}>{error}</p>}

        <p style={{
          color: "#8991a2", fontSize: 11, lineHeight: 1.5,
          margin: "22px 0 0", textAlign: "center",
        }}>Development testing mode · OTP appears in the backend terminal</p>
      </section>
    </main>
  );
}
