import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/700.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
});

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;

// The PRODUCTION Clerk instance uses a custom Frontend API domain
// (clerk.plutustrading.tech) that serves Clerk's static script bundles WITHOUT
// CORS headers, so the browser refuses them (failed_to_load_clerk_js). Work
// around it by loading the two bundles (clerk-js + @clerk/ui) from jsDelivr,
// which returns proper CORS — but ONLY for the prod (pk_live) key. The dev
// (pk_test) key uses *.clerk.accounts.dev, which serves the scripts correctly,
// so it must be left on Clerk's default (undefined => Clerk picks the URL).
// Note: jsDelivr does NOT resolve the @1 range tag for @clerk/ui, so the UI
// bundle is pinned to an exact version (current `latest`). Bump it when Clerk
// upgrades, or override via VITE_CLERK_JS_URL / VITE_CLERK_UI_URL.
const isProdKey = !!PUBLISHABLE_KEY?.startsWith("pk_live_");
const CLERK_JS_URL =
  (import.meta.env.VITE_CLERK_JS_URL as string | undefined) ||
  (isProdKey ? "https://cdn.jsdelivr.net/npm/@clerk/clerk-js@6/dist/clerk.browser.js" : undefined);
const CLERK_UI_URL =
  (import.meta.env.VITE_CLERK_UI_URL as string | undefined) ||
  (isProdKey ? "https://cdn.jsdelivr.net/npm/@clerk/ui@1.23.0/dist/ui.browser.js" : undefined);

const clerkAppearance = {
  variables: {
    colorBackground: "#131109",
    colorInputBackground: "#1e1c16",
    colorInputText: "#ffffff",
    colorPrimary: "hsl(39,100%,52%)",
    colorText: "#ffffff",
    colorTextSecondary: "#b0a890",
    colorTextOnPrimaryBackground: "#1a1400",
    colorNeutral: "#888070",
    colorDanger: "hsl(4,84%,58%)",
    colorSuccess: "hsl(145,60%,46%)",
    borderRadius: "0.25rem",
    fontFamily: '"IBM Plex Sans", -apple-system, sans-serif',
    fontSize: "0.875rem",
  },
  elements: {
    card: {
      background: "#131109",
      border: "1px solid #2a2720",
      boxShadow: "none",
      padding: "1.75rem",
    },
    headerTitle: { color: "#ffffff", fontWeight: "700" },
    headerSubtitle: { color: "#b0a890" },
    formFieldLabel: { color: "#b0a890", fontSize: "0.75rem" },
    formFieldInput: {
      background: "#1e1c16",
      borderColor: "#2a2720",
      color: "#ffffff",
    },
    formButtonPrimary: {
      background: "hsl(39,100%,52%)",
      color: "#1a1400",
      fontFamily: '"JetBrains Mono", ui-monospace, monospace',
      fontWeight: "700",
      fontSize: "0.7rem",
      letterSpacing: "0.08em",
      textTransform: "uppercase" as const,
      boxShadow: "none",
    },
    socialButtonsBlockButton: {
      background: "#1e1c16",
      border: "1px solid #2a2720",
      color: "#ffffff",
    },
    socialButtonsBlockButtonText: { color: "#ffffff" },
    socialButtonsBlockButtonArrow: { color: "#ffffff" },
    badge: { color: "#ffffff", background: "#2a2720" },
    dividerLine: { background: "#2a2720" },
    dividerText: { color: "#666050" },
    footerActionLink: { color: "hsl(39,100%,52%)" },
    footerActionText: { color: "#b0a890" },
    identityPreviewText: { color: "#ffffff" },
    identityPreviewEditButton: { color: "hsl(39,100%,52%)" },
    otpCodeFieldInput: {
      background: "#1e1c16",
      borderColor: "#2a2720",
      color: "#ffffff",
    },
    alertText: { color: "#ffffff" },
  },
};

async function mount() {
  const root = document.getElementById("root")!;
  if (PUBLISHABLE_KEY) {
    const { ClerkProvider } = await import("@clerk/react");
    ReactDOM.createRoot(root).render(
      <React.StrictMode>
        <ClerkProvider publishableKey={PUBLISHABLE_KEY} __internal_clerkJSUrl={CLERK_JS_URL} __internal_clerkUIUrl={CLERK_UI_URL} afterSignOutUrl="/" afterSignInUrl="/" afterSignUpUrl="/" appearance={clerkAppearance}>
          <QueryClientProvider client={queryClient}>
            <App clerkEnabled />
          </QueryClientProvider>
        </ClerkProvider>
      </React.StrictMode>,
    );
  } else {
    ReactDOM.createRoot(root).render(
      <React.StrictMode>
        <QueryClientProvider client={queryClient}>
          <App clerkEnabled={false} />
        </QueryClientProvider>
      </React.StrictMode>,
    );
  }
}

mount();
