import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  auth: { login: vi.fn(), register: vi.fn() },
  setToken: vi.fn(),
}));

import { auth, setToken } from "../api";
import Login from "./Login";

const user = { id: 1, email: "a@b.co", full_name: "A", role: "buyer" } as any;

function renderLogin(onLogin = vi.fn(), url = "/login") {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Login onLogin={onLogin} />
    </MemoryRouter>,
  );
  return onLogin;
}

function type(placeholder: string, value: string) {
  fireEvent.change(screen.getByPlaceholderText(placeholder), { target: { value } });
}

describe("Login page", () => {
  beforeEach(() => {
    vi.mocked(auth.login).mockReset();
    vi.mocked(auth.register).mockReset();
    vi.mocked(setToken).mockReset();
  });

  it("signs in, stores the token and reports the user", async () => {
    vi.mocked(auth.login).mockResolvedValue({ access_token: "tok", user });
    const onLogin = renderLogin();

    type("Email", "a@b.co");
    type("Password", "secret-pass");
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => expect(onLogin).toHaveBeenCalledWith(user));
    expect(auth.login).toHaveBeenCalledWith("a@b.co", "secret-pass");
    expect(setToken).toHaveBeenCalledWith("tok");
  });

  it("shows the error message and does not log in when the API rejects", async () => {
    vi.mocked(auth.login).mockRejectedValue(new Error("Invalid credentials"));
    const onLogin = renderLogin();

    type("Email", "a@b.co");
    type("Password", "wrong");
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
    expect(onLogin).not.toHaveBeenCalled();
    expect(setToken).not.toHaveBeenCalled();
  });

  it("pre-fills only the buyer demo account from the ?demo=buyer link, never the admin", () => {
    renderLogin(vi.fn(), "/login?demo=buyer");
    expect(screen.getByPlaceholderText("Email")).toHaveValue("demo.buyer@spendintel.io");
  });

  it("does not pre-fill anything without the demo link", () => {
    renderLogin();
    expect(screen.getByPlaceholderText("Email")).toHaveValue("");
    expect(screen.getByPlaceholderText("Password")).toHaveValue("");
  });

  it("register mode offers only buyer/finance roles (no admin) and sends the chosen role", async () => {
    vi.mocked(auth.register).mockResolvedValue({ access_token: "tok2", user });
    renderLogin();

    fireEvent.click(screen.getByRole("button", { name: "New user? Register" }));
    const roles = screen.getAllByRole("option").map((o) => (o as HTMLOptionElement).value);
    expect(roles).toEqual(["buyer", "finance"]);

    type("Full name", "Ada L");
    type("Email", "ada@b.co");
    type("Password", "a-long-password");
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "finance" } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));

    await waitFor(() => expect(auth.register).toHaveBeenCalledWith("ada@b.co", "a-long-password", "Ada L", "finance"));
  });
});
