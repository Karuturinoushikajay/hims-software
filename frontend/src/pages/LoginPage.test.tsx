import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "@/i18n";
import { LoginPage } from "./LoginPage";


describe("LoginPage", () => {
  it("renders username and password fields", async () => {
    const onLoggedIn = vi.fn();
    render(<LoginPage onLoggedIn={onLoggedIn} />);
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/username/i), "facadmin");
    expect(screen.getByLabelText(/username/i)).toHaveValue("facadmin");
  });
});
