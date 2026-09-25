import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import DashboardPage from "../src/pages/DashboardPage";
import { complaint, renderWithRouter, stubFetch } from "./helpers";

const page = (items: unknown[], total = items.length) => ({
  body: { items, total, page: 1, page_size: 10 },
});

describe("Operations queue", () => {
  it("lists complaints with their triage provenance", async () => {
    stubFetch([page([complaint()])]);
    renderWithRouter(<DashboardPage />);

    expect(await screen.findByText(/burst main flooding since dawn/i)).toBeInTheDocument();
    expect(screen.getByText("llm:groq")).toBeInTheDocument();
    expect(screen.getByText(/1 reports/)).toBeInTheDocument();
  });

  it("surfaces the server's 409 message verbatim", async () => {
    stubFetch([
      page([complaint({ status: "rejected" })]),
      {
        status: 409,
        body: {
          error: "invalid_transition",
          message: "cannot transition from rejected to resolved",
          attempted: { from: "rejected", to: "resolved" },
          allowed: [],
        },
      },
    ]);
    renderWithRouter(<DashboardPage />);

    await screen.findByText(/burst main flooding since dawn/i);
    await userEvent.click(screen.getByRole("button", { name: "Resolved" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("cannot transition from rejected to resolved");
  });

  it("applies an accepted transition without a reload", async () => {
    stubFetch([
      page([complaint({ status: "open" })]),
      { status: 200, body: complaint({ status: "in_progress" }) },
    ]);
    renderWithRouter(<DashboardPage />);

    await screen.findByText(/burst main flooding since dawn/i);
    await userEvent.click(screen.getByRole("button", { name: "In progress" }));

    await waitFor(() => expect(screen.getByRole("cell", { name: "In progress" })).toBeInTheDocument());
    // The row now offers "Open" as a move, which it did not before the change.
    expect(screen.getByRole("button", { name: "Open" })).toBeInTheDocument();
  });

  it("invites action instead of showing an empty table", async () => {
    stubFetch([page([], 0)]);
    renderWithRouter(<DashboardPage />);

    expect(await screen.findByText(/nothing matches these filters/i)).toBeInTheDocument();
  });
});
