import type { State } from "./types";
export const statusLabels: Record<State, string> = {
  RECEIVED: "Received",
  CLASSIFYING: "Classifying",
  EXTRACTING: "Extracting",
  VALIDATING: "Validating",
  NEEDS_INFORMATION: "Needs information",
  PENDING_APPROVAL: "Awaiting approval",
  EXECUTING: "Executing",
  COMPLETED: "Completed",
  REJECTED: "Rejected",
  NEEDS_MANUAL_REVIEW: "Manual review",
};
export const workingStates: State[] = [
  "RECEIVED",
  "CLASSIFYING",
  "EXTRACTING",
  "VALIDATING",
  "EXECUTING",
];
export function titleCase(text: string) {
  return text.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
export function dateTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}
export function shortId(value: string) {
  return value.slice(0, 8).toUpperCase();
}
export function percent(value: number | undefined) {
  return value == null ? "Not reported" : `${Math.round(value * 100)}%`;
}
export function bytes(value: number) {
  return value < 1000 ? `${value} B` : `${(value / 1000).toFixed(1)} KB`;
}
