import { useState } from "react";
import CryptoBridgeLogo from "./CryptoBridgeLogo";
import { authShell, card, field, fieldLabel, primaryButton, subTabBar, subTab, textMuted, textHeading } from "../../utils/workspace/workspaceClasses";

export default function AuthPanel({ mode, setMode, form, setForm, onSubmit, pending, message }) {
  const isRegister = mode === "register";

  return (
    <div className={authShell()}>
      <div className={`w-full max-w-md ${card("overflow-hidden shadow-2xl p-6 space-y-6")}`}>
        <div className="text-center space-y-2">
          <CryptoBridgeLogo size={48} iconOnly className="inline-flex" />
          <h2 className={`text-xl font-extrabold tracking-wide uppercase ${textHeading()}`}>
            CryptoBridge Trading Desk
          </h2>
          <p className={`text-xs ${textMuted()}`}>
            Delta Exchange India Options Execution Terminal
          </p>
        </div>

        <div className={subTabBar()}>
          <button
            type="button"
            onClick={() => setMode("login")}
            className={`flex-1 rounded-lg px-3 py-2 text-xs font-bold uppercase ${
              !isRegister ? "bg-lime-400 text-zinc-950" : textMuted()
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => setMode("register")}
            className={`flex-1 rounded-lg px-3 py-2 text-xs font-bold uppercase ${
              isRegister ? "bg-lime-400 text-zinc-950" : textMuted()
            }`}
          >
            Register
          </button>
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
          className="space-y-4"
        >
          {isRegister ? (
            <div>
              <label className={fieldLabel()}>
                Display Name
              </label>
              <input
                type="text"
                value={form.displayName}
                onChange={(event) => setForm((current) => ({ ...current, displayName: event.target.value }))}
                className={field("font-sans")}
                placeholder="e.g. John Doe"
                required
              />
            </div>
          ) : null}

          <div>
            <label className={fieldLabel()}>
              Email Address
            </label>
            <input
              type="email"
              value={form.email}
              onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
              className={field("font-sans")}
              required
            />
          </div>

          <div>
            <label className={fieldLabel()}>
              Password
            </label>
            <input
              type="password"
              value={form.password}
              onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
              className={field()}
              required
            />
          </div>

          {message ? (
            <div className="bg-red-50 dark:bg-red-950/40 border border-red-300 dark:border-red-500/30 rounded p-2.5 text-[11px] text-red-700 dark:text-red-400 text-center font-semibold">
              {message}
            </div>
          ) : null}

          <button type="submit" disabled={pending} className={`w-full py-2.5 ${primaryButton("disabled:bg-zinc-800 disabled:text-zinc-500")}`}>
            {pending ? "Working..." : isRegister ? "Register Trading Account" : "Sign In Securely"}
          </button>
        </form>
      </div>
    </div>
  );
}
