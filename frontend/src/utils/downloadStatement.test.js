import { downloadFailureMessage, downloadStatement } from "./downloadStatement";

beforeEach(() => {
  jest.useFakeTimers();
  window.URL.createObjectURL = jest.fn(() => "blob:test-file");
  window.URL.revokeObjectURL = jest.fn();
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});

test("downloads real PDF/XLSX payloads and revokes object URLs after the click", async () => {
  const click = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const pdf = new Blob(["%PDF-1.4\ncontent"], { type: "application/pdf" });
  const pdfName = await downloadStatement({
    data: pdf,
    headers: { "content-type": "application/pdf", "content-disposition": "attachment; filename=statement.pdf" },
  }, { format: "pdf", fallbackFilename: "fallback.pdf" });
  expect(pdfName).toBe("statement.pdf");
  expect(window.URL.createObjectURL).toHaveBeenCalledWith(pdf);
  expect(click).toHaveBeenCalledTimes(1);
  expect(window.URL.revokeObjectURL).not.toHaveBeenCalled();
  jest.advanceTimersByTime(1000);
  expect(window.URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-file");
  const xlsx = new Blob([Uint8Array.of(0x50, 0x4b, 0x03, 0x04, 0x00)], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const xlsxName = await downloadStatement({
    data: xlsx,
    headers: {
      "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "content-disposition": "attachment; filename=statement.xlsx",
    },
  }, { format: "xlsx", fallbackFilename: "fallback.xlsx" });
  expect(xlsxName).toBe("statement.xlsx");
  expect(click).toHaveBeenCalledTimes(2);
  click.mockRestore();
});

test("rejects JSON/HTML error bodies instead of downloading them", async () => {
  const json = new Blob([JSON.stringify({ detail: "Not authorized." })], { type: "application/json" });
  await expect(downloadStatement({ data: json, headers: { "content-type": "application/json" } }, {
    format: "xlsx", fallbackFilename: "x.xlsx",
  })).rejects.toThrow("Not authorized.");
  expect(window.URL.createObjectURL).not.toHaveBeenCalled();

  expect(await downloadFailureMessage({ response: { data: json } }, "Fallback")).toBe("Not authorized.");
});
