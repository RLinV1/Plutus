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

// Load clerk-js from the public CDN instead of the custom Frontend API domain
// (clerk.plutustrading.tech). The custom domain serves the static bundle without
// CORS headers and is flagged by ad/privacy blockers (ERR_BLOCKED_BY_CLIENT);
// jsDelivr returns proper CORS and is allowlisted by blockers. Auth API calls
// still go to the domain encoded in the publishable key. Override with
// VITE_CLERK_JS_URL if needed. Keep the @6 major in sync with the pk_live key.
const CLERK_JS_URL =
  (import.meta.env.VITE_CLERK_JS_URL as string | undefined) ||
  "https://cdn.jsdelivr.net/npm/@clerk/clerk-js@6/dist/clerk.browser.js";

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
        <ClerkProvider publishableKey={PUBLISHABLE_KEY} clerkJSUrl={CLERK_JS_URL} afterSignOutUrl="/" afterSignInUrl="/" afterSignUpUrl="/" appearance={clerkAppearance}>
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
