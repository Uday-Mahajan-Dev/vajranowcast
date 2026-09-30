"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldAlert,
  Zap,
  Radio,
  Send,
  RefreshCw,
  Clock,
  MapPin,
  CheckCircle2,
  AlertCircle,
  ArrowLeft,
  Flame,
  Info,
} from "lucide-react";
import Link from "next/link";
import { INDIAN_CITIES } from "@/lib/constants";
import { createTestAlert, generateAlerts, fetchActiveAlerts } from "@/lib/api";
import { AlertResponse } from "@/lib/types";
import { formatProbability, formatValidityWindow, formatISTTime } from "@/lib/utils";

export default function StaffConsolePage() {
  const [selectedCity, setSelectedCity] = useState<string>("Delhi");
  const [selectedTier, setSelectedTier] = useState<string>("warning");
  const [leadTime, setLeadTime] = useState<number>(1);
  const [adminToken, setAdminToken] = useState<string>("");

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitResult, setSubmitResult] = useState<{ success: boolean; message: string } | null>(null);

  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanResult, setScanResult] = useState<{ success: boolean; message: string } | null>(null);

  const [activeAlerts, setActiveAlerts] = useState<AlertResponse[]>([]);
  const [isLoadingAlerts, setIsLoadingAlerts] = useState<boolean>(false);

  // Load saved token from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("vajra_staff_token") || "vajra_admin_secret_token_dev";
    setAdminToken(saved);
    loadAlerts();
  }, []);

  const handleTokenChange = (val: string) => {
    setAdminToken(val);
    localStorage.setItem("vajra_staff_token", val);
  };

  const loadAlerts = async () => {
    setIsLoadingAlerts(true);
    try {
      const res = await fetchActiveAlerts();
      setActiveAlerts(res.alerts || []);
    } catch {
      // Ignore
    } finally {
      setIsLoadingAlerts(false);
    }
  };

  const handleSendTestAlert = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!adminToken) {
      setSubmitResult({ success: false, message: "Please provide an Admin Token or Meteorologist JWT." });
      return;
    }

    setIsSubmitting(true);
    setSubmitResult(null);

    try {
      const res = await createTestAlert(adminToken, {
        city: selectedCity,
        tier: selectedTier,
        lead_time_hours: leadTime,
      });

      setSubmitResult({
        success: true,
        message: `Drill alert for ${selectedCity} (${selectedTier.toUpperCase()}) created successfully! Expiring in 15 minutes.`,
      });
      loadAlerts();
    } catch (err: any) {
      setSubmitResult({
        success: false,
        message: err?.message || "Failed to create drill alert. Verify authentication credentials.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTriggerScan = async () => {
    if (!adminToken) {
      setScanResult({ success: false, message: "Please provide an Admin Token or Meteorologist JWT." });
      return;
    }

    setIsScanning(true);
    setScanResult(null);

    try {
      const res = await generateAlerts(adminToken);
      setScanResult({
        success: true,
        message: `Scan complete: ${res.alerts_generated} operational alerts generated/updated across 10 cities.`,
      });
      loadAlerts();
    } catch (err: any) {
      setScanResult({
        success: false,
        message: err?.message || "Failed to trigger scan. Check token permissions.",
      });
    } finally {
      setIsScanning(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-50 p-4 text-slate-900 dark:bg-slate-950 dark:text-white md:p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Navigation & Header */}
        <div className="flex items-center justify-between border-b border-slate-200 pb-4 dark:border-slate-800">
          <div>
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 text-xs font-bold text-teal-600 hover:underline dark:text-teal-400 mb-1"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Back to Live Radar Map
            </Link>
            <h1 className="text-xl font-black text-slate-900 dark:text-white flex items-center gap-2">
              <ShieldAlert className="h-6 w-6 text-teal-600 dark:text-teal-400" />
              Staff Operations &amp; Drill Console
            </h1>
          </div>
          <span className="rounded-full bg-teal-500/20 px-3 py-1 text-xs font-bold text-teal-700 dark:text-teal-300 border border-teal-500/30">
            Staff Access
          </span>
        </div>

        {/* Authentication Card */}
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/80">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
            Authorization Credentials
          </h2>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="password"
              value={adminToken}
              onChange={(e) => handleTokenChange(e.target.value)}
              placeholder="Enter Admin Token (e.g. vajra_admin_secret_token_dev) or JWT"
              className="flex-1 rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-900 outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
          </div>
          <p className="mt-1.5 text-[11px] text-slate-400">
            Requires meteorologist role in Supabase Auth or valid X-Admin-Token.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Form 1: Send Test Alert */}
          <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/80 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                <Radio className="h-4 w-4 text-amber-500" />
                Transmit Simulated Drill Alert
              </h2>
              <span className="rounded bg-test-striped px-1.5 py-0.5 text-[9px] font-black uppercase text-white shadow-xs">
                Drill Only
              </span>
            </div>

            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Creates a transient drill alert marked with <strong className="text-amber-500">is_test=true</strong> and an automatic <strong>15-minute expiration</strong> window. Real alerts cannot be created here.
            </p>

            <form onSubmit={handleSendTestAlert} className="space-y-3.5 text-xs">
              {/* City Selection */}
              <div>
                <label className="font-bold text-slate-700 dark:text-slate-300 block mb-1">
                  Target Indian City:
                </label>
                <select
                  value={selectedCity}
                  onChange={(e) => setSelectedCity(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-slate-50 p-2 text-xs font-semibold text-slate-900 outline-none focus:border-teal-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                >
                  {INDIAN_CITIES.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name} ({c.state})
                    </option>
                  ))}
                </select>
              </div>

              {/* Alert Tier Selection */}
              <div>
                <label className="font-bold text-slate-700 dark:text-slate-300 block mb-1">
                  Alert Severity Tier:
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { key: "watch", label: "Watch (35%)", color: "border-yellow-500 text-yellow-600" },
                    { key: "advisory", label: "Advisory (45%)", color: "border-orange-500 text-orange-600" },
                    { key: "warning", label: "Warning (65%)", color: "border-red-500 text-red-600" },
                  ].map((t) => (
                    <button
                      type="button"
                      key={t.key}
                      onClick={() => setSelectedTier(t.key)}
                      className={`rounded-xl border p-2 text-center font-bold text-xs transition-all ${
                        selectedTier === t.key
                          ? `bg-slate-900 text-white dark:bg-white dark:text-slate-900 ring-2 ring-teal-500`
                          : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Lead Time Selection */}
              <div>
                <label className="font-bold text-slate-700 dark:text-slate-300 block mb-1">
                  Lead Time Window:
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {[1, 2, 3].map((lt) => (
                    <button
                      type="button"
                      key={lt}
                      onClick={() => setLeadTime(lt)}
                      className={`rounded-xl border p-2 text-center font-bold text-xs transition-all ${
                        leadTime === lt
                          ? "bg-teal-600 text-white shadow-sm"
                          : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                      }`}
                    >
                      +{lt} hour{lt > 1 ? "s" : ""}
                    </button>
                  ))}
                </div>
              </div>

              {submitResult && (
                <div
                  className={`rounded-xl p-2.5 text-xs font-medium leading-relaxed flex items-start gap-2 ${
                    submitResult.success
                      ? "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 border border-emerald-500/20"
                      : "bg-rose-500/10 text-rose-800 dark:text-rose-300 border border-rose-500/20"
                  }`}
                >
                  {submitResult.success ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
                  ) : (
                    <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
                  )}
                  <span>{submitResult.message}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-amber-500 py-2.5 font-bold text-slate-950 shadow-md hover:bg-amber-400 transition-all disabled:opacity-50"
              >
                {isSubmitting ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                <span>Send Drill Alert (Expires in 15m)</span>
              </button>
            </form>
          </div>

          {/* Action 2: Routine City Scan & Status */}
          <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/80 space-y-4">
            <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
              <Zap className="h-4 w-4 text-teal-600 dark:text-teal-400" />
              Automated 10-City Nowcast Scan
            </h2>

            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Triggers the operational backend inference pipeline across all 10 major metros (Delhi, Mumbai, Kolkata, Chennai, Bengaluru, Hyderabad, Jaipur, Lucknow, Guwahati, Nagpur), evaluating predictions against WATCH (≥30%), ADVISORY (≥40%), and WARNING (≥60%) tiers.
            </p>

            <button
              onClick={handleTriggerScan}
              disabled={isScanning}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-teal-600 py-2.5 font-bold text-white shadow-md hover:bg-teal-700 transition-all disabled:opacity-50 text-xs"
            >
              {isScanning ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Flame className="h-4 w-4" />
              )}
              <span>Run City Scan Batch (/api/v1/alerts/generate)</span>
            </button>

            {scanResult && (
              <div
                className={`rounded-xl p-2.5 text-xs font-medium leading-relaxed flex items-start gap-2 ${
                  scanResult.success
                    ? "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 border border-emerald-500/20"
                    : "bg-rose-500/10 text-rose-800 dark:text-rose-300 border border-rose-500/20"
                }`}
              >
                {scanResult.success ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
                ) : (
                  <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
                )}
                <span>{scanResult.message}</span>
              </div>
            )}

            <div className="rounded-xl bg-slate-100/70 p-3 text-[11px] text-slate-500 dark:bg-slate-800/50 dark:text-slate-400 space-y-1">
              <div className="font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1">
                <Info className="h-3.5 w-3.5 text-teal-600" />
                De-duplication Policy
              </div>
              <p>
                Active alerts are de-duplicated per city. Re-running a scan updates active records in Supabase rather than spawning duplicates.
              </p>
            </div>
          </div>
        </div>

        {/* Live Active Alerts Table */}
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/80 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Clock className="h-4 w-4 text-teal-600" />
              Live Active Alerts in Supabase ({activeAlerts.length})
            </h2>
            <button
              onClick={loadAlerts}
              disabled={isLoadingAlerts}
              className="flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <RefreshCw className={`h-3 w-3 ${isLoadingAlerts ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>

          {activeAlerts.length === 0 && !isLoadingAlerts && (
            <div className="py-6 text-center text-xs text-slate-400">
              No active alerts in the database. Send a test drill alert above to verify.
            </div>
          )}

          {activeAlerts.length > 0 && (
            <div className="divide-y divide-slate-100 dark:divide-slate-800/60 text-xs">
              {activeAlerts.map((a) => (
                <div key={a.alert_id} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="space-y-0.5">
                    <div className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
                      <MapPin className="h-3.5 w-3.5 text-rose-500" />
                      <span>{a.city}</span>
                      <span className="rounded px-1.5 py-0.2 text-[9px] font-bold uppercase bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                        {a.tier || a.severity}
                      </span>
                      {a.is_test && (
                        <span className="rounded bg-test-striped px-1.5 py-0.2 text-[8px] font-black uppercase text-white">
                          TEST DRILL
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-600 dark:text-slate-300">{a.message}</p>
                    <p className="text-[10px] text-slate-400">
                      Valid: {formatValidityWindow(a.valid_from, a.valid_until)}
                    </p>
                  </div>
                  <div className="text-right font-mono text-[11px] shrink-0">
                    <div className="font-bold text-teal-600 dark:text-teal-400">
                      P(TS): {formatProbability(a.thunderstorm_probability)}
                    </div>
                    <div className="text-slate-400 text-[10px]">
                      P(Lt): {formatProbability(a.lightning_probability)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
