/**
 * UI component tests: queue row, states, and the approval-gated action panel.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { EmptyState, ErrorState, QueueRow } from "@/components/ui";
import { ActionPanel } from "@/components/ActionPanel";
import type { ActionOut, AlertSummary } from "@/lib/api";

const alert: AlertSummary = {
  id: "ALR-2026-10-0011",
  title: "Suspicious sign-in: ana.rios from unrecognised external IP",
  severity: "high",
  alert_type: "auth_anomaly",
  ts: "2026-10-12T09:14:00Z",
  source: "idp-anomaly",
  incident_id: null,
  status: "new",
  tags: [],
};

describe("QueueRow", () => {
  it("renders severity, title, id and status", () => {
    render(<QueueRow alert={alert} selected={false} onSelect={() => {}} />);
    expect(screen.getByText("high")).toBeTruthy();
    expect(screen.getByText(alert.title)).toBeTruthy();
    expect(screen.getByText("ALR-2026-10-0011")).toBeTruthy();
    expect(screen.getByText("new")).toBeTruthy();
  });

  it("fires onSelect on click", () => {
    const onSelect = vi.fn();
    render(<QueueRow alert={alert} selected={false} onSelect={onSelect} />);
    fireEvent.click(screen.getByText(alert.title));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});

describe("state components", () => {
  it("ErrorState surfaces the message", () => {
    render(<ErrorState message="Cannot reach backend at http://localhost:8000" />);
    expect(screen.getByText(/Cannot reach backend/)).toBeTruthy();
  });

  it("EmptyState shows title and hint", () => {
    render(
      <EmptyState title="No investigation selected" hint="Pick an alert from the queue." />,
    );
    expect(screen.getByText("No investigation selected")).toBeTruthy();
    expect(screen.getByText("Pick an alert from the queue.")).toBeTruthy();
  });
});

function makeAction(overrides: Partial<ActionOut>): ActionOut {
  return {
    id: "act:1",
    incident_id: "INC-2026-TEST",
    action_type: "BLOCK_IP",
    target_id: "ip:203.0.113.44",
    description: "Add ip:203.0.113.44 to the egress blocklist (SIMULATED).",
    status: "PROPOSED",
    evidence_ids: ["evi:1"],
    created_by: "demo.analyst",
    created_at: "2026-10-12T10:00:00Z",
    decided_at: null,
    decided_by: null,
    decision_reason: null,
    simulated: true,
    ...overrides,
  };
}

describe("ActionPanel approval gate", () => {
  it("shows approve/reject only for PROPOSED actions", () => {
    render(
      <ActionPanel
        incidentId="INC-2026-TEST"
        actions={[
          makeAction({ id: "act:prop", status: "PROPOSED" }),
          makeAction({ id: "act:app", status: "APPROVED" }),
          makeAction({ id: "act:rej", status: "REJECTED" }),
        ]}
        onActionsChanged={() => {}}
        analyst="demo.analyst"
      />,
    );
    // Two buttons: approve + reject for the single PROPOSED action.
    expect(screen.getByText("approve").closest("button")).toBeTruthy();
    expect(screen.getByText("reject").closest("button")).toBeTruthy();
    expect(screen.getAllByText("approve")).toHaveLength(1);
    expect(screen.getAllByText("reject")).toHaveLength(1);
    expect(screen.getAllByText("PROPOSED")).toHaveLength(1);
    expect(screen.getByText("APPROVED")).toBeTruthy();
    expect(screen.getByText("REJECTED")).toBeTruthy();
  });

  it("renders simulated badge and warns that nothing real executes", () => {
    render(
      <ActionPanel
        incidentId="INC-2026-TEST"
        actions={[makeAction({})]}
        onActionsChanged={() => {}}
        analyst="demo.analyst"
      />,
    );
    expect(screen.getByText("approval required")).toBeTruthy();
    expect(screen.getByText(/Nothing is executed against real systems/)).toBeTruthy();
  });

  it("shows an empty state when no incident exists yet", () => {
    render(
      <ActionPanel
        incidentId={null}
        actions={[]}
        onActionsChanged={() => {}}
        analyst="demo.analyst"
      />,
    );
    expect(screen.getByText("No incident yet")).toBeTruthy();
  });
});

describe("ActionPanel two-step confirmation", () => {
  it("requires an explicit confirm and can be cancelled", () => {
    render(
      <ActionPanel
        incidentId="INC-2026-TEST"
        actions={[makeAction({})]}
        onActionsChanged={() => {}}
        analyst="demo.analyst"
      />,
    );
    fireEvent.click(screen.getByText("approve"));
    expect(screen.getByText(/approve this simulated action\?/)).toBeTruthy();
    expect(screen.getByText("confirm approve")).toBeTruthy();
    fireEvent.click(screen.getByText("cancel"));
    expect(screen.getByText("approve")).toBeTruthy();
  });
});
