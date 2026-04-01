import { describe, it, expect } from "vitest";
import { validateZipFile } from "../repoZipScan";

describe("validateZipFile", () => {
	it("should pass for a file with zip MIME type", () => {
		const file = new File(["content"], "archive.zip", { type: "application/zip" });
		const result = validateZipFile(file);
		expect(result.valid).toBe(true);
		expect(result.error).toBeUndefined();
	});

	it("should pass for a file with .zip extension even without zip MIME type", () => {
		const file = new File(["content"], "archive.zip", { type: "" });
		const result = validateZipFile(file);
		expect(result.valid).toBe(true);
	});

	it("should pass for a file with application/x-zip-compressed type", () => {
		const file = new File(["content"], "archive", { type: "application/x-zip-compressed" });
		const result = validateZipFile(file);
		expect(result.valid).toBe(true);
	});

	it("should fail for a non-ZIP file type without .zip extension", () => {
		const file = new File(["content"], "document.pdf", { type: "application/pdf" });
		const result = validateZipFile(file);
		expect(result.valid).toBe(false);
		expect(result.error).toBeDefined();
	});

	it("should fail for a file exceeding 500MB", () => {
		const size = 500 * 1024 * 1024 + 1; // 500MB + 1 byte
		const file = new File(["x"], "big.zip", { type: "application/zip" });
		Object.defineProperty(file, "size", { value: size });
		const result = validateZipFile(file);
		expect(result.valid).toBe(false);
		expect(result.error).toBeDefined();
	});

	it("should pass for a file at exactly 500MB", () => {
		const size = 500 * 1024 * 1024; // exactly 500MB
		const file = new File(["x"], "exact.zip", { type: "application/zip" });
		Object.defineProperty(file, "size", { value: size });
		const result = validateZipFile(file);
		expect(result.valid).toBe(true);
	});
});
