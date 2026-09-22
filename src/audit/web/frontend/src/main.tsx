import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./styles.css";

// Defaults for every query in the app. These are the app's main data-fetching
// knobs, so they are worth stating rather than leaving to be inferred:
//
//   retry: 1              The API is local. A failure is usually a real error
//                         worth showing, not a flaky network worth hiding, so
//                         retry once and then surface it.
//   staleTime: 5_000      Report data is immutable once a scan completes; the
//                         5s window mainly stops sibling components mounting
//                         in the same tick from each fetching the same record.
//   refetchOnWindowFocus  Off. Alt-tabbing back to a long issue table should
//                         not reload it under the reader.
//
// Views that need fresher data than this set their own options. ScanDetail
// polls while a scan is running, and the protected identity context opts out
// of caching entirely.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root container");

// Match Vite's `base`, production bundle is served under /app/, dev is /.
const BASENAME = import.meta.env.PROD ? "/app" : "/";

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={BASENAME}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
