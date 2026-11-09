
import { useEffect, useMemo, useState } from "react";
import { AllCommunityModule, themeQuartz } from "ag-grid-community";
import { AgGridProvider, AgGridReact } from "ag-grid-react";
import { inr, get, post } from "../api.js";

const money = (value) => inr(Number(value || 0));

const dateFormat = (value) => {
  if (!value) return "—";
  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
};

const statusLabel = (status) => ({
  ACTIVE: "Active",
  REBOOKED: "Replaced",
  CANCELLED: "Cancelled",
}[status] || status || "—");

const paymentLabel = (type) => ({
  PREPAID: "Prepaid",
  POSTPAID: "Pay after",
  PAY_AFTER: "Pay after",
}[type] || type || "—");

const normalizeSearch = (value) =>
  String(value ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

const editDistance = (a, b) => {
  if (Math.abs(a.length - b.length) > 2) return 99;

  let previous = Array.from(
    { length: b.length + 1 },
    (_, i) => i
  );

  for (let i = 1; i <= a.length; i++) {
    const current = [i];

    for (let j = 1; j <= b.length; j++) {
      current[j] = Math.min(
        current[j - 1] + 1,
        previous[j] + 1,
        previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
      );
    }

    previous = current;
  }

  return previous[b.length];
};

const isSubsequence = (query, word) => {
  let index = 0;

  for (const char of word) {
    if (char === query[index]) index++;
    if (index === query.length) return true;
  }

  return false;
};

const fuzzyMatch = (query, value) => {
  const text = normalizeSearch(value);
  if (!text) return false;
  if (text.includes(query)) return true;
  if (query.length <= 1) return false;

  return text.split(/\s+/).some((word) => {
    if (word.includes(query)) return true;

    if (query.length >= 3 && isSubsequence(query, word)) {
      return true;
    }

    if (query.length >= 4) {
      const errors = query.length >= 7 ? 2 : 1;
      if (editDistance(query, word) <= errors) return true;
    }

    return false;
  });
};

export default function Transactions({ bookings = [] }) {
  const [search, setSearch] = useState("");
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [paymentRecords, setPaymentRecords] = useState({});
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [paymentError, setPaymentError] = useState("");
  const [captureBusy, setCaptureBusy] = useState(false);
  const [screenWidth, setScreenWidth] = useState(
    typeof window !== "undefined" ? window.innerWidth : 1200
  );

  useEffect(() => {
    const resize = () => setScreenWidth(window.innerWidth);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadPaymentHistory() {
      const ids = [...new Set(
        bookings.map((booking) => booking.id ?? booking.booking_id).filter(Boolean)
      )];

      if (!ids.length) {
        setPaymentRecords({});
        return;
      }

      setPaymentLoading(true);
      setPaymentError("");

      const results = await Promise.allSettled(
        ids.map(async (id) => ({
          id: String(id),
          payments: await get(`/api/payments/by-booking/${encodeURIComponent(id)}`),
        }))
      );

      if (cancelled) return;

      const next = {};
      const failures = [];

      results.forEach((result, index) => {
        if (result.status === "fulfilled") {
          next[result.value.id] = Array.isArray(result.value.payments)
            ? result.value.payments
            : [];
        } else {
          failures.push(ids[index]);
        }
      });

      setPaymentRecords(next);
      setPaymentError(
        failures.length
          ? "Some payment records could not be loaded. Please refresh and try again."
          : ""
      );
      setPaymentLoading(false);
    }

    loadPaymentHistory();

    return () => {
      cancelled = true;
    };
  }, [bookings]);

  const rows = useMemo(
    () =>
      bookings.map((booking) => {
        const id = String(booking.id ?? booking.booking_id ?? "");
        const payments = paymentRecords[id] || [];

        return {
          ...booking,
          payments,
          latest_payment: payments[payments.length - 1] || null,
          booking_status: statusLabel(booking.status),
          payment_label: paymentLabel(booking.payment_type),
          booking_date: dateFormat(booking.created_at),
        };
      }),
    [bookings, paymentRecords]
  );

  const filteredRows = useMemo(() => {
    const query = normalizeSearch(search);
    if (!query) return rows;

    const queryWords = query.split(/\s+/).filter(Boolean);

    return rows.filter((booking) => {
      const values = [
        ...Object.values(booking).filter(
          (value) =>
            value !== null &&
            value !== undefined &&
            ["string", "number"].includes(typeof value)
        ),
        money(booking.amount),
        dateFormat(booking.created_at),
        statusLabel(booking.status),
        paymentLabel(booking.payment_type),
      ];

      return queryWords.every((word) =>
        values.some((value) => fuzzyMatch(word, value))
      );
    });
  }, [rows, search]);

  useEffect(() => {
    if (!selectedBooking) return;

    const key = (booking) =>
      String(booking.id ?? booking.booking_id ?? booking.label);

    const updated = rows.find(
      (booking) => key(booking) === key(selectedBooking)
    );

    setSelectedBooking(updated || null);
  }, [rows]);

  const columns = useMemo(() => {
    const mobile = screenWidth <= 600;
    const compact = screenWidth <= 1000;

    return [
      {
        field: "label",
        headerName: "BOOKING DETAILS",
        minWidth: mobile ? 175 : 205,
        flex: 2.2,
        tooltipField: "label",
      },
      {
        field: "trip_title",
        headerName: "DESTINATION",
        minWidth: 130,
        flex: 1.3,
        hide: compact,
        tooltipField: "trip_title",
      },
      {
        field: "kind",
        headerName: "TYPE",
        minWidth: 85,
        maxWidth: 105,
        flex: 0.8,
        hide: mobile,
      },
      {
        field: "amount",
        headerName: "AMOUNT",
        minWidth: 105,
        flex: 1,
        valueFormatter: (params) => money(params.value),
      },
      {
        field: "payment_label",
        headerName: "PAYMENT",
        minWidth: 105,
        flex: 1,
        hide: compact,
      },
      {
        field: "booking_status",
        headerName: "STATUS",
        minWidth: 95,
        flex: 1,
      },
      {
        field: "booking_date",
        headerName: "DATE",
        minWidth: 115,
        flex: 1,
        hide: compact,
      },
    ];
  }, [screenWidth]);

  const total = rows.reduce(
    (sum, booking) => sum + Number(booking.amount || 0),
    0
  );

  const active = rows.filter(
    (booking) => booking.status === "ACTIVE"
  ).length;

  const closeDetails = () => setSelectedBooking(null);

  const [startBusy, setStartBusy] = useState(false);

  const startPayPalPayment = async () => {
    if (!selectedBooking || startBusy) return;

    const bookingId = selectedBooking.id ?? selectedBooking.booking_id;
    if (!bookingId) {
      setPaymentError("Booking ID is missing.");
      return;
    }

    if (selectedBooking.status !== "ACTIVE" || selectedBooking.payment_type !== "PREPAID") {
      setPaymentError("Only active prepaid bookings can be paid here.");
      return;
    }

    setStartBusy(true);
    setPaymentError("");

    try {
      const result = await post("/api/payments/start", {
        booking_id: String(bookingId),
      });

      if (!/^https:\/\/www\.(sandbox\.)?paypal\.com\//.test(result.approve_url || "")) {
        throw new Error("PayPal approval link was not returned by the server.");
      }

      window.location.assign(result.approve_url);
    } catch (error) {
      setPaymentError(error.message || "Could not start PayPal payment.");
      setStartBusy(false);
    }
  };

  const captureAuthorizedPayment = async () => {
    const payment = selectedBooking?.latest_payment;
    if (!payment || payment.status !== "AUTHORIZED" || captureBusy) return;

    const confirmed = window.confirm(
      `Confirm capture of ${money(payment.amount_inr)} for this booking?`
    );
    if (!confirmed) return;

    setCaptureBusy(true);
    setPaymentError("");

    try {
      const updated = await post(`/api/payments/${payment.id}/capture`);
      const bookingId = String(
        selectedBooking.id ?? selectedBooking.booking_id
      );

      setPaymentRecords((current) => ({
        ...current,
        [bookingId]: (current[bookingId] || []).map((item) =>
          item.id === updated.id ? updated : item
        ),
      }));
    } catch (error) {
      setPaymentError(error.message || "Payment capture failed.");
    } finally {
      setCaptureBusy(false);
    }
  };

  return (
    <div className="transactions">
      <div className="tx-summary">
        <div className="tx-summary-card">
          <span>Total booking value</span>
          <strong>{money(total)}</strong>
          <small>Across all bookings</small>
        </div>

        <div className="tx-summary-card">
          <span>Total records</span>
          <strong>{rows.length}</strong>
          <small>All transactions</small>
        </div>

        <div className="tx-summary-card">
          <span>Active bookings</span>
          <strong>{active}</strong>
          <small>Currently active</small>
        </div>
      </div>

      <div className="tx-toolbar">
        <div className="tx-heading">
          <h4>All transactions</h4>
          <p>Find and manage your travel bookings.</p>
        </div>

        <div className="tx-search-wrap">
          <span className="tx-search-icon">⌕</span>

          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search bookings, trips, status..."
            aria-label="Search transactions"
          />

          {search && (
            <button
              type="button"
              className="tx-clear-search"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              ×
            </button>
          )}
        </div>
      </div>

      <div className="tx-result-line">
        <span>
          {search
            ? `${filteredRows.length} matching result${
                filteredRows.length === 1 ? "" : "s"
              }`
            : `Showing all ${rows.length} bookings`}
        </span>

        {search && (
          <button type="button" onClick={() => setSearch("")}>
            Clear search
          </button>
        )}
      </div>

      {rows.length === 0 ? (
        <div className="tx-empty">
          <div className="tx-empty-icon">▤</div>
          <h4>No transactions yet</h4>
          <p>Your travel bookings will appear here.</p>
        </div>
      ) : filteredRows.length === 0 ? (
        <div className="tx-empty">
          <div className="tx-empty-icon">⌕</div>
          <h4>No matching bookings found</h4>
          <p>Try another destination, booking name, type or status.</p>
          <button type="button" onClick={() => setSearch("")}>
            Clear search
          </button>
        </div>
      ) : (
        <AgGridProvider modules={[AllCommunityModule]}>
          <div className="tx-grid">
            <AgGridReact
              theme={themeQuartz}
              rowData={filteredRows}
              columnDefs={columns}
              defaultColDef={{
                sortable: true,
                filter: false,
                resizable: false,
                floatingFilter: false,
                suppressHeaderMenuButton: true,
                minWidth: 80,
              }}
              pagination={filteredRows.length > 8}
              paginationPageSize={8}
              paginationPageSizeSelector={[8, 15, 25]}
              animateRows={true}
              getRowId={(params) =>
                String(
                  params.data.id ??
                  params.data.booking_id ??
                  params.data.label
                )
              }
              onRowClicked={(event) =>
                setSelectedBooking(event.data)
              }
              rowClass="tx-clickable-row"
            />
          </div>
        </AgGridProvider>
      )}

      {selectedBooking && (
        <div
          className="tx-detail-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeDetails();
            }
          }}
        >
          <aside
            className="tx-detail-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tx-detail-title"
          >
            <div className="tx-detail-header">
              <div>
                <span className="tx-detail-eyebrow">
                  BOOKING DETAILS
                </span>
                <h3 id="tx-detail-title">Transaction overview</h3>
              </div>

              <button
                type="button"
                className="tx-detail-close"
                onClick={closeDetails}
                aria-label="Close booking details"
              >
                ×
              </button>
            </div>

            <div className="tx-detail-amount">
              <span>Booking amount</span>
              <strong>{money(selectedBooking.amount)}</strong>
              <span
                className={`tx-status-pill ${
                  selectedBooking.status === "ACTIVE"
                    ? "is-active"
                    : selectedBooking.status === "CANCELLED"
                    ? "is-cancelled"
                    : "is-other"
                }`}
              >
                {statusLabel(selectedBooking.status)}
              </span>
            </div>

            <div className="tx-detail-section">
              <h4>Booking information</h4>

              <div className="tx-detail-row">
                <span>Booking ID</span>
                <strong>
                  {selectedBooking.booking_id ??
                    selectedBooking.id ??
                    "—"}
                </strong>
              </div>

              <div className="tx-detail-row">
                <span>Booking name</span>
                <strong>{selectedBooking.label || "—"}</strong>
              </div>

              <div className="tx-detail-row">
                <span>Trip / Destination</span>
                <strong>{selectedBooking.trip_title || "—"}</strong>
              </div>

              <div className="tx-detail-row">
                <span>Booking type</span>
                <strong>{selectedBooking.kind || "—"}</strong>
              </div>

              <div className="tx-detail-row">
                <span>Booking date</span>
                <strong>{dateFormat(selectedBooking.created_at)}</strong>
              </div>
            </div>

            <div className="tx-detail-section">
              <h4>Payment information</h4>

              <div className="tx-detail-row">
                <span>Payment type</span>
                <strong>
                  {paymentLabel(selectedBooking.payment_type)}
                </strong>
              </div>

              <div className="tx-detail-row">
                <span>Booking status</span>
                <strong>{statusLabel(selectedBooking.status)}</strong>
              </div>

              <div className="tx-detail-row">
                <span>Total amount</span>
                <strong>{money(selectedBooking.amount)}</strong>
              </div>

              <div className="tx-detail-row">
                <span>Payment status</span>
                <strong>
                  {selectedBooking.latest_payment?.status || "No payment record"}
                </strong>
              </div>

              {selectedBooking.latest_payment && (
                <>
                  <div className="tx-detail-row">
                    <span>Payment ID</span>
                    <strong>{selectedBooking.latest_payment.id}</strong>
                  </div>
                  <div className="tx-detail-row">
                    <span>PayPal order</span>
                    <strong>{selectedBooking.latest_payment.order_id || "?"}</strong>
                  </div>
                </>
              )}

              {selectedBooking.status === "ACTIVE" &&
                selectedBooking.payment_type === "PREPAID" &&
                !["CAPTURED", "AUTHORIZED"].includes(selectedBooking.latest_payment?.status) && (
                  <button
                    type="button"
                    className="tx-detail-done"
                    disabled={startBusy}
                    onClick={startPayPalPayment}
                  >
                    {startBusy ? "Opening PayPal..." : "Pay with PayPal"}
                  </button>
                )}

              {selectedBooking.latest_payment?.status === "AUTHORIZED" && (
                <button
                  type="button"
                  className="tx-detail-done"
                  disabled={captureBusy}
                  onClick={captureAuthorizedPayment}
                >
                  {captureBusy ? "Processing..." : "Confirm and capture payment"}
                </button>
              )}

              {paymentLoading && <small>Loading payment history...</small>}
              {paymentError && <small role="alert">{paymentError}</small>}
            </div>

            <button
              type="button"
              className="tx-detail-done"
              onClick={closeDetails}
            >
              Done
            </button>
          </aside>
        </div>
      )}
    </div>
  );
}
