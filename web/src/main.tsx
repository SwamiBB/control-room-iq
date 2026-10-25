import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Operator from "./views/Operator";
import Viewer from "./views/Viewer";
import Multiview from "./views/Multiview";
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
        <Route path="/operator" element={<Operator />} />
        <Route path="/viewer" element={<Viewer />} />
        <Route path="/multiview" element={<Multiview />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
