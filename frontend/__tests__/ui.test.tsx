/**
 * UI component tests: queue row, states, and the approval-gated action panel.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { EmptyState, ErrorState, QueueRow } from "@/components/ui";
import { ActionPanel } from "@/components/ActionPanel";
import { api, type ActionOut, type AlertSummary } from "@/lib/api";

// Mock the two API methods the action panel calls, keeping the rest real.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, decide: vi.fn(), actions: vi.fn() },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.actions).mockResolvedValue({ count: 0, actions: [] });
});

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
    // A cancelled confirmation must never hit the API.
    expect(api.decide).not.toHaveBeenCalled();
  });

  it("calls decide exactly once after confirming an approval", async () => {
    const onActionsChanged = vi.fn();
    const approved = makeAction({ id: "act:prop", status: "APPROVED" });
    vi.mocked(api.decide).mockResolvedValue(approved);
    vi.mocked(api.actions).mockResolvedValue({ count: 1, actions: [approved] });

    render(
      <ActionPanel
        incidentId="INC-2026-TEST"
        actions={[makeAction({ id: "act:prop", status: "PROPOSED" })]}
        onActionsChanged={onActionsChanged}
        analyst="demo.analyst"
      />,
    );
    // First click only stages: no API call yet.
    fireEvent.click(screen.getByText("approve"));
    expect(api.decide).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("confirm approve"));
    await waitFor(() => expect(api.decide).toHaveBeenCalledTimes(1));
    expect(api.decide).toHaveBeenCalledWith(
      "act:prop",
      "approve",
      "demo.analyst",
      expect.stringContaining("approve"),
    );
    await waitFor(() => expect(api.actions).toHaveBeenCalledWith("INC-2026-TEST"));
    await waitFor(() => expect(onActionsChanged).toHaveBeenCalledWith([approved]));
    // Staged state is cleared after the successful submit.
    expect(screen.queryByText("confirm approve")).toBeNull();
  });

  it("calls decide exactly once after confirming a rejection", async () => {
    const onActionsChanged = vi.fn();
    const rejected = makeAction({ id: "act:prop", status: "REJECTED" });
    vi.mocked(api.decide).mockResolvedValue(rejected);
    vi.mocked(api.actions).mockResolvedValue({ count: 1, actions: [rejected] });

    render(
      <ActionPanel
        incidentId="INC-2026-TEST"
        actions={[makeAction({ id: "act:prop", status: "PROPOSED" })]}
        onActionsChanged={onActionsChanged}
        analyst="demo.analyst"
      />,
    );
    fireEvent.click(screen.getByText("reject"));
    expect(api.decide).not.toHaveBeenCalled(); // staged, not submitted
    fireEvent.click(screen.getByText("confirm reject"));
    await waitFor(() => expect(api.decide).toHaveBeenCalledTimes(1));
    expect(api.decide).toHaveBeenCalledWith(
      "act:prop",
      "reject",
      "demo.analyst",
      expect.stringContaining("reject"),
    );
    await waitFor(() => expect(onActionsChanged).toHaveBeenCalledWith([rejected]));
    expect(screen.queryByText("confirm reject")).toBeNull();
  });

  it("keeps the staged decision visible when the API fails (no silent loss)", async () => {
    vi.mocked(api.decide).mockRejectedValue(new Error("boom: backend 500"));

    render(
      <ActionPanel
        incidentId="INC-2026-TEST"
        actions={[makeAction({ id: "act:prop", status: "PROPOSED" })]}
        onActionsChanged={() => {}}
        analyst="demo.analyst"
      />,
    );
    fireEvent.click(screen.getByText("approve"));
    fireEvent.click(screen.getByText("confirm approve"));

    // Error surfaced, decision still staged so the analyst can retry or cancel.
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByText(/boom: backend 500/)).toBeTruthy();
    expect(screen.getByText("confirm approve")).toBeTruthy();
    expect(api.decide).toHaveBeenCalledTimes(1);

    // Retry works and is still a single call per confirm click.
    fireEvent.click(screen.getByText("confirm approve"));
    await waitFor(() => expect(api.decide).toHaveBeenCalledTimes(2));
  });

  it("does not call decide while a decision is in flight (no duplicate submit)", async () => {
    let resolveDecide!: (v: ActionOut) => void;
    vi.mocked(api.decide).mockImplementation(
      () => new Promise((res) => { resolveDecide = res; }),
    );
    vi.mocked(api.actions).mockResolvedValue({
      count: 1,
      actions: [makeAction({ id: "act:prop", status: "APPROVED" })],
    });

    render(
      <ActionPanel
        incidentId="INC-2026-TEST"
        actions={[makeAction({ id: "act:prop", status: "PROPOSED" })]}
        onActionsChanged={() => {}}
        analyst="demo.analyst"
      />,
    );
    fireEvent.click(screen.getByText("approve"));
    fireEvent.click(screen.getByText("confirm approve"));
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: /confirm approve/i }) as HTMLButtonElement)
          .disabled,
      ).toBe(true),
    );
    // Button is disabled while in flight: further clicks are no-ops.
    fireEvent.click(screen.getByRole("button", { name: /confirm approve/i }));
    expect(api.decide).toHaveBeenCalledTimes(1);
    resolveDecide(makeAction({ id: "act:prop", status: "APPROVED" }));
    await waitFor(() => expect(api.decide).toHaveBeenCalledTimes(1));
  });

  it("clears the staged decision when the selected incident changes", () => {
    const props = {
      actions: [makeAction({ id: "act:prop", status: "PROPOSED" as const })],
      onActionsChanged: () => {},
      analyst: "demo.analyst",
    };
    const { rerender } = render(<ActionPanel incidentId="INC-A" {...props} />);
    fireEvent.click(screen.getByText("approve"));
    expect(screen.getByText(/approve this simulated action\?/)).toBeTruthy();

    rerender(<ActionPanel incidentId="INC-B" {...props} />);
    expect(screen.queryByText("confirm approve")).toBeNull();
    expect(screen.getByText("approve")).toBeTruthy();
    expect(api.decide).not.toHaveBeenCalled();
  });

  it("moves focus to the confirm button when staging, and back on cancel", async () => {
    render(
      <ActionPanel
        incidentId="INC-2026-TEST"
        actions={[makeAction({ id: "act:prop", status: "PROPOSED" })]}
        onActionsChanged={() => {}}
        analyst="demo.analyst"
      />,
    );
    const approveBtn = screen.getByRole("button", { name: /approve/i });
    approveBtn.focus();
    fireEvent.click(approveBtn);
    await waitFor(() =>
      expect(document.activeElement?.textContent).toContain("confirm approve"),
    );

    fireEvent.click(screen.getByText("cancel"));
    await waitFor(() =>
      expect(document.activeElement?.textContent).toContain("approve"),
    );
    expect(api.decide).not.toHaveBeenCalled();
  });
});
