import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Register from "./Register";
import api from "../api/axios";

jest.mock("../api/axios", () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

jest.mock("../components/SelfieCapture", () => function MockSelfieCapture() {
  return <div aria-label="Selfie upload test placeholder" />;
});

function renderRegistration() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="/" element={<h1>Sign in</h1>} />
      </Routes>
    </MemoryRouter>
  );
}

function changeField(container, name, value) {
  fireEvent.change(container.querySelector(`[name="${name}"]`), { target: { value } });
}

function enterPersonalDetails(container) {
  changeField(container, "first_name", "Synthetic");
  changeField(container, "last_name", "Applicant");
  changeField(container, "email", "signup.synthetic@example.invalid");
  changeField(container, "date_of_birth", "1990-01-01");
  fireEvent.click(screen.getByRole("button", { name: /Next: Contact Info/ }));
}

function enterContactDetails(container) {
  changeField(container, "national_id", "28750187");
  changeField(container, "phone_number", "0712345678");
  changeField(container, "county", "Nairobi");
  changeField(container, "address", "Synthetic test address");
}

function enterSecurityDetails(container) {
  changeField(container, "username", "synthetic_applicant");
  changeField(container, "password", "Strongpass1");
  changeField(container, "confirm_password", "Strongpass1");
}

beforeEach(() => jest.clearAllMocks());

test("successful signup submits consent and enters the success state", async () => {
  api.post.mockResolvedValueOnce({ data: { member_number: "SACCO000001", id_status: "draft" } });
  const { container } = renderRegistration();
  enterPersonalDetails(container);
  enterContactDetails(container);
  fireEvent.click(screen.getByRole("button", { name: /Next: Set Password/ }));
  enterSecurityDetails(container);
  fireEvent.click(screen.getByRole("button", { name: /Complete Registration/ }));

  expect(await screen.findByText("Registration successful. Your Member Number is SACCO000001. Redirecting…")).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledTimes(1);
  const [url, payload] = api.post.mock.calls[0];
  expect(url).toBe("register/");
  expect(payload.get("username")).toBe("synthetic_applicant");
  expect(payload.get("id_verification_consent")).toBe("false");
  expect(screen.getByRole("button", { name: "Registration complete" })).toBeDisabled();
});

test("server upload errors return to Step 2, appear beside the upload, and preserve entered details", async () => {
  api.post.mockRejectedValueOnce({
    response: { status: 400, data: { id_document: ["The PDF file is incomplete or invalid."] } },
  });
  const { container } = renderRegistration();
  enterPersonalDetails(container);
  enterContactDetails(container);

  const upload = new File(["%PDF-1.4"], "identity.pdf", { type: "application/pdf" });
  fireEvent.change(container.querySelector("#id-document-input"), { target: { files: [upload] } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: /Next: Set Password/ }));
  enterSecurityDetails(container);
  fireEvent.click(screen.getByRole("button", { name: /Complete Registration/ }));

  expect(await screen.findByText("The PDF file is incomplete or invalid.")).toBeInTheDocument();
  expect(container.querySelector("#id-document-input")).toHaveAttribute("aria-invalid", "true");
  expect(container.querySelector('[name="national_id"]')).toHaveValue("28750187");

  fireEvent.click(screen.getByRole("button", { name: /Back/ }));
  expect(container.querySelector('[name="first_name"]')).toHaveValue("Synthetic");
  fireEvent.click(screen.getByRole("button", { name: /Next: Contact Info/ }));
  expect(container.querySelector('[name="national_id"]')).toHaveValue("28750187");
  expect(screen.getByText("The PDF file is incomplete or invalid.")).toBeInTheDocument();
  expect(screen.getByText("identity.pdf is selected and will be submitted.")).toBeInTheDocument();
});
