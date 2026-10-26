import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Operator from "./views/Operator";
import Viewer from "./views/Viewer";
import Multiview from "./views/Multiview";
import ErrorBoundary from "./components/ErrorBoundary";
// Condensed type for the viewer's broadcast graphics, shipped with the app so every machine draws the same.
import "@fontsource/barlow-condensed/500.css";
import "@fontsource/barlow-condensed/600.css";
import "@fontsource/barlow-condensed/700.css";
import "./styles.css";

function Home() {
  return (
    <main className="home">
      <h1>Control Room IQ</h1>
      <p>An AI operator for the live production control room.</p>
      <nav>
        <Link to="/operator">Operator console</Link> · <Link to="/viewer">Viewer experience</Link> ·{" "}
        <Link to="/multiview">Multiviewer</Link>
      </nav>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        {/* Keyed per route: the boundaries sit in the same place, so without a key a caught error on one page
            would follow the operator to the next. */}
        <Route path="/operator" element={<ErrorBoundary key="operator" name="Operator console"><Operator /></ErrorBoundary>} />
        <Route path="/viewer" element={<ErrorBoundary key="viewer" name="Viewer"><Viewer /></ErrorBoundary>} />
        <Route path="/multiview" element={<ErrorBoundary key="multiview" name="Multiviewer"><Multiview /></ErrorBoundary>} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
