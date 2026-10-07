import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A mutable stand-in for the build-time config, so each test picks its own deployment.
const cfg = vi.hoisted(() => ({ restUrl: "http://rest", anonKey: "", apiUrl: "" }));
vi.mock("../config", () => ({ config: cfg }));

import { TryIt } from "./TryIt";

const photo = () => new File([new Uint8Array([255, 216, 255])], "plant.jpg", { type: "image/jpeg" });

beforeEach(() => {
  cfg.apiUrl = "https://api.example";
});
afterEach(() => vi.unstubAllGlobals());

describe("TryIt", () => {
  it("explains itself when no analysis service is deployed, instead of offering a button that cannot work", () => {
    cfg.apiUrl = "";
    render(<TryIt />);
    expect(screen.getByText(/not connected to this deployment/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyse" })).not.toBeInTheDocument();
  });

  it("sends nothing until a photo is chosen", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<TryIt />);
    await userEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the photo to the chosen task and shows a plant answer with its caveat", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          answer: "Lantana camara",
          best_guess: "Lantana camara",
          probability: 0.93,
          threshold: 0.76,
          kind: "invasive",
          alternatives: [],
          context: null,
          notice: "A model's guess, not a verified identification.",
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<TryIt />);
    await userEvent.upload(screen.getByLabelText("Choose a photo"), photo());
    await userEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(await screen.findByText(/an invasive species/)).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.example/api/v1/infer/plants");
    expect(init.method).toBe("POST");
    expect(screen.getByText(/not a verified identification/)).toBeInTheDocument();
  });

  it("is honest when the model is unsure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ answer: "unknown", best_guess: "Senna spectabilis", probability: 0.4, threshold: 0.76, kind: null, alternatives: [], context: null, notice: "n" }),
          { status: 200 },
        ),
      ),
    );
    render(<TryIt />);
    await userEvent.upload(screen.getByLabelText("Choose a photo"), photo());
    await userEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(await screen.findByText("Not sure.")).toBeInTheDocument();
    expect(screen.queryByText(/an invasive species/)).not.toBeInTheDocument();
  });

  it("translates a rate limit into advice", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "slow down" }), { status: 429 })));
    render(<TryIt />);
    await userEvent.upload(screen.getByLabelText("Choose a photo"), photo());
    await userEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many requests");
  });

  it("explains a sleeping free-tier service rather than showing a raw network error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    render(<TryIt />);
    await userEvent.upload(screen.getByLabelText("Choose a photo"), photo());
    await userEvent.click(screen.getByRole("button", { name: "Analyse" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/may take about a minute to wake/);
  });

  it("disables the button while a request is running, so one click is one request", async () => {
    let finish: (r: Response) => void = () => undefined;
    const fetchMock = vi.fn(() => new Promise<Response>((r) => (finish = r)));
    vi.stubGlobal("fetch", fetchMock);
    render(<TryIt />);
    await userEvent.upload(screen.getByLabelText("Choose a photo"), photo());
    await userEvent.click(screen.getByRole("button", { name: "Analyse" }));
    const busy = await screen.findByRole("button", { name: "Analysing…" });
    expect(busy).toBeDisabled();
    await userEvent.click(busy);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    finish(new Response(JSON.stringify({ detail: "x" }), { status: 503 }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Analyse" })).toBeEnabled());
    expect(screen.getByRole("alert")).toHaveTextContent("not available");
  });
});
