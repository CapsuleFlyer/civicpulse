import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import SubmitPage from "../src/pages/SubmitPage";
import { complaint, renderWithRouter, stubFetch } from "./helpers";

describe("Report a problem", () => {
  it("blocks a submission that the server would reject anyway", async () => {
    const fetchStub = stubFetch([]);
    renderWithRouter(<SubmitPage />);

    await userEvent.type(screen.getByLabelText(/what is happening/i), "flood");
    await userEvent.click(screen.getByRole("button", { name: /send report/i }));

    expect(await screen.findByText(/at least 10 characters/i)).toBeInTheDocument();
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("shows the category, priority, summary and which provider decided them", async () => {
    stubFetch([{ status: 201, body: complaint() }]);
    renderWithRouter(<SubmitPage />);

    await userEvent.type(
      screen.getByLabelText(/what is happening/i),
      "Burst water main flooding Street 12 since fajr.",
    );
    await userEvent.type(screen.getByLabelText(/where is it/i), "Street 12, G-9/1");
    await userEvent.click(screen.getByRole("button", { name: /send report/i }));

    await waitFor(() => expect(screen.getByText(/logged as reference/i)).toBeInTheDocument());
    expect(screen.getByText("water")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("llm:groq")).toBeInTheDocument();
    expect(screen.getByText(/812 ms/)).toBeInTheDocument();
  });

  it("explains a fallback triage instead of hiding it", async () => {
    stubFetch([{ status: 201, body: complaint({ triaged_by: "rules:fallback" }) }]);
    renderWithRouter(<SubmitPage />);

    await userEvent.type(
      screen.getByLabelText(/what is happening/i),
      "Sewerage overflowing outside the mosque gate for three days.",
    );
    await userEvent.type(screen.getByLabelText(/where is it/i), "Street 4, I-8/2");
    await userEvent.click(screen.getByRole("button", { name: /send report/i }));

    expect(await screen.findByText(/model was unavailable/i)).toBeInTheDocument();
  });

  it("renders the server's field errors when validation disagrees", async () => {
    stubFetch([
      {
        status: 400,
        body: {
          error: "validation_error",
          message: "the submission was rejected: location",
          fields: [{ field: "location", message: "String should have at least 3 characters" }],
        },
      },
    ]);
    renderWithRouter(<SubmitPage />);

    await userEvent.type(
      screen.getByLabelText(/what is happening/i),
      "Streetlights of the whole lane are out since Monday.",
    );
    await userEvent.type(screen.getByLabelText(/where is it/i), "G-9");
    await userEvent.click(screen.getByRole("button", { name: /send report/i }));

    expect(await screen.findByText(/at least 3 characters/i)).toBeInTheDocument();
  });
});
