import { Routes, Route, Link } from "react-router";
import Operator from "./views/Operator";
import Viewer from "./views/Viewer";
import Multiview from "./views/Multiview";
import ErrorBoundary from "./components/ErrorBoundary";

/** The app's pages, apart from the router that serves them: main.tsx mounts them in the browser's, tests in memory. */
export const PATHS = ["/", "/operator", "/operator-demo", "/viewer", "/multiview"] as const;

export function Home() {
  return (
    <main className="home">
      <h1>Control Room IQ</h1>
      <p>An AI operator for the live production control room.</p>
      <nav>
        <Link to="/operator">Operator console</Link> ·{" "}
        <Link to="/operator-demo">Operator with architecture overlay</Link> ·{" "}
        <Link to="/viewer">Viewer experience</Link> ·{" "}
        <Link to="/multiview">Multiviewer</Link>
      </nav>
    </main>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      {/* Keyed per route: the boundaries sit in the same place, so without a key a caught error on one page
          would follow the operator to the next. */}
      <Route path="/operator" element={<ErrorBoundary key="operator" name="Operator console"><Operator /></ErrorBoundary>} />
      <Route path="/operator-demo" element={<ErrorBoundary key="operator-demo" name="Operator console"><Operator demo /></ErrorBoundary>} />
      <Route path="/viewer" element={<ErrorBoundary key="viewer" name="Viewer"><Viewer /></ErrorBoundary>} />
      <Route path="/multiview" element={<ErrorBoundary key="multiview" name="Multiviewer"><Multiview /></ErrorBoundary>} />
    </Routes>
  );
}
