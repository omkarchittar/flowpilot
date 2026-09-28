"use client";
export default function ErrorBoundary({ reset }: { reset: () => void }) {
  return (
    <div className="full-state">
      <h1>This view could not load</h1>
      <p>
        Your submitted work remains on the server. Try loading the view again.
      </p>
      <button className="button" onClick={reset}>
        Try again
      </button>
    </div>
  );
}
